import abc
from enum import Enum, unique
import numpy as np
from scipy.optimize import fmin_l_bfgs_b

from typing import List

"""
Meucci - Fully Flexible Views: Theory and practice 
"""

@unique
class ViewType(Enum):

    Equality = 0
    LargerThan = 1
    SmallerThan = 2


class View(abc.ABC):

    def __init__(self, view_type: ViewType):

        """
        Constructor

        Parameters
        ----------
        view_type
            Specifies view type.
        """

        self.view_type = view_type

    @abc.abstractmethod
    def get_constraint_matrix(self):
        raise NotImplementedError("Abstract member get_constraint_matrix not implemented")

    @abc.abstractmethod
    def get_constraint_vector(self):
        raise NotImplementedError("Abstract member get_constraint_vector not implemented")


class MeanView(View):

    """
    Class that implements a mean view.
    """

    def __init__(self, view_type: ViewType, factor: np.ndarray, mean_target: float):

        """
        Constructor

        Parameters
        ----------
        view_type
            Specifies view type.
        factor:
            Factor for which we have a view
        mean_target:
            Expected value of target under the view.
        """

        super(MeanView, self).__init__(view_type)

        self.constraint_matrix = factor
        self.constraint_vector = mean_target

    def get_constraint_matrix(self):

        return self.constraint_matrix

    def get_constraint_vector(self):

        return self.constraint_vector


class VolatilityView(View):

    """
    Class that implements a volatility view.
    """

    def __init__(self, view_type: ViewType, factor: np.ndarray, expected_value: float, vol_target: float):

        """
        Constructor

        Parameters
        ----------
        view_type
            Specifies view type.
        factor:
            Factor for which we have a view
        expected_value:
            Expected value of factor.
        vol_target:
            Volatility of factor under view.
        """

        super(VolatilityView, self).__init__(view_type)

        self.constraint_matrix = factor**2
        self.constraint_vector = vol_target**2 + expected_value**2

    def get_constraint_matrix(self):
        return self.constraint_matrix

    def get_constraint_vector(self):
        return self.constraint_vector


class CorrelationView(View):

    """
    Class that implements a correlation view.
    """

    def __init__(self, view_type: ViewType, first_factor: np.ndarray, second_factor: np.ndarray,
                 first_expected_value: float, second_expected_value: float, first_vol: float,
                 second_vol: float, correlation_target: float):
        """
        Constructor

        Parameters
        ----------
        view_type
            Specifies view type.
        first_factor:
            Factor for which we have a view
        second_factor:
            Factor for which we have a view
        first_expected_value:
            Expected value of first factor.
        second_expected_value:
            Expected value of second factor.
        first_vol:
            Volatility of first factor.
        second_vol:
            Volatility of second factor
        correlation_target:
            Correlation target under view.
        """

        super(CorrelationView, self).__init__(view_type)

        self.constraint_matrix = first_factor * second_factor
        self.constraint_vector = correlation_target * first_vol * second_vol + first_expected_value * second_expected_value

    def get_constraint_matrix(self):
        return self.constraint_matrix

    def get_constraint_vector(self):
        return self.constraint_vector


class ProbabilitySolver:

    def __init__(self, initial_probs: np.ndarray, views: List[View]):

        """
        Constructor

        Parameters
        ----------
        initial_probs:
            Initial probabilities.
        views:
            List of Views.
        """

        self.init_probs = initial_probs
        self.init_log_probs = np.log(initial_probs)

        self.total_constraint_matrix = None
        self.total_constraint_matrix_t = None
        self.total_constraint_vector = None
        self.is_inequality_constraint = []

        # prepare views for solving probabilities
        self.prepare_constraints(views)

    def store_inequality(self, constraint_vector, is_inequality: bool):

        """
        Functions that stores a boolean indicator for whether the constraint is inequality or not.

        Parameters
        ----------
        constraint_vector:
            Constraint vector.
        is_inequality:
            Bolean indicator.


        Returns
        -------
        NoReturn

        """

        if isinstance(constraint_vector, float) or isinstance(constraint_vector, float):
            self.is_inequality_constraint.append(is_inequality)

        else:
            self.is_inequality_constraint.append([is_inequality for _ in constraint_vector])

    def prepare_constraints(self, views: List[View]):

        """
        Function that prepares constraints.

        Parameters
        ----------
        views:
            List of vies.

        Returns
        -------
        NoReturn

        """

        size = len(self.init_probs)
        self.total_constraint_matrix = np.ones((1, size))
        self.total_constraint_vector = np.ones(1)
        self.store_inequality(1.0, False)

        for view in views:
            if view.view_type == ViewType.Equality:
                self.total_constraint_matrix = np.vstack((self.total_constraint_matrix, view.get_constraint_matrix()))
                self.total_constraint_vector = np.vstack((self.total_constraint_vector, view.get_constraint_vector()))
                self.store_inequality(view.get_constraint_vector(), False)
            elif view.view_type == ViewType.LargerThan:
                self.total_constraint_matrix = np.vstack((self.total_constraint_matrix, -view.get_constraint_matrix()))
                self.total_constraint_vector = np.vstack((self.total_constraint_vector, -view.get_constraint_vector()))
                self.store_inequality(view.get_constraint_vector(), True)
            elif view.view_type == ViewType.SmallerThan:
                self.total_constraint_matrix = np.vstack((self.total_constraint_matrix, view.get_constraint_matrix()))
                self.total_constraint_vector = np.vstack((self.total_constraint_vector, view.get_constraint_vector()))
                self.store_inequality(view.get_constraint_vector(), True)
            else:
                raise Exception('Unknown ViewType')

        self.total_constraint_matrix_t = np.transpose(self.total_constraint_matrix)
        self.total_constraint_vector = self.total_constraint_vector.flatten()

    def objective_function(self, params: np.ndarray) -> float:

        """
        Objective function.

        See https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1213325 for further details.

        Parameters
        ----------
        params:
            Parameter vector to optimize over (lagrange multipliers).

        Returns
        -------
        float
            The Lagrange dual function (negative).

        """

        x = self.calculate_probabilities(params)
        x = np.maximum(x, 10 ** (-32))

        lagrangian = x.T @ (np.log(x) - self.init_log_probs) + params @ (self.total_constraint_matrix @ x -
                                                                         self.total_constraint_vector)

        return -lagrangian

    def calculate_probabilities(self, params: np.ndarray) -> np.ndarray:

        """
        Calculates probabilities

        Parameters
        ----------
        params:
            Parameter vector to optimize over (lagrange multipliers).

        Returns
        -------
        np.ndarray
            Vector of probabilities.


        """

        x = self.init_log_probs - 1.0 - (self.total_constraint_matrix_t @ params).flatten()

        return np.exp(x)

    def minimize_entropy(self):

        """
        Minimize entropy to obtain probabilities under the views.

        Returns
        -------
        np.ndarray
            Probabilities.

        """

        # initial parameters
        init_params = np.repeat(0.01, len(self.is_inequality_constraint))

        # add zero bound for inequality constraints
        bounds = [(0.0, None) if _ else (None, None) for _ in self.is_inequality_constraint]

        # optimization
        # TODO:: Add analytical gradient and hessian
        opt_params, f, d = fmin_l_bfgs_b(self.objective_function, init_params, bounds=bounds,
                                         approx_grad=True)

        # calculate probs
        probs = self.calculate_probabilities(opt_params)

        if np.abs(1.0 - np.sum(probs)) > 0.001:

            raise Exception('Entropy optimization did not converge')

        return probs
