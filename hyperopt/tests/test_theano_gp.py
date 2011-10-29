"""
Tests of hyperopt.theano_gp
"""

__authors__   = "James Bergstra, Dan Yamins"
__copyright__ = "(c) 2011, James Bergstra, Dan Yamins"
__license__   = "3-clause BSD License"
__contact__   = "github.com/jaberg/hyperopt"

import unittest

import numpy
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt

import theano
from theano import tensor
from theano.tests.unittest_tools import verify_grad, seed_rng

from hyperopt.idxs_vals_rnd import IdxsValsList
from hyperopt.bandits import TwoArms
from hyperopt.base import Bandit, BanditAlgo
from hyperopt.theano_gp import GP_BanditAlgo
from hyperopt.ht_dist2 import rSON2, normal
from hyperopt.genson_bandits import GensonBandit
from hyperopt.experiments import SerialExperiment
from hyperopt.dbn import Dummy_DBN_Base
import hyperopt.plotting

from hyperopt.theano_gp import SparseGramSet
from hyperopt.theano_gp import SparseGramGet
from hyperopt.theano_gp import sparse_gram_get
from hyperopt.theano_gp import sparse_gram_set
from hyperopt.theano_gp import sparse_gram_inc

from hyperopt.theano_gp import sparse_gram_mul


class GPAlgo(GP_BanditAlgo):
    use_base_suggest = True
    xlim_low = -5
    xlim_high = 5
    def suggest_from_model(self, trials, results, N):
        if self.use_base_suggest:
            return GP_BanditAlgo.suggest_from_model(self,
                    trials, results, N)

        ivls = self.idxs_vals_by_status(trials, results)
        X_IVLs = ivls['x_IVLs']
        Ys = ivls['losses']
        Ys_var = ivls['losses_variance']
        prepared_data = self.prepare_GP_training_data(ivls)
        x_all, y_all, y_mean, y_var, y_std = prepared_data
        self.fit_GP(*prepared_data)

        candidates = self._prior_sampler(5)
        EI = self.GP_EI(IdxsValsList.fromflattened(candidates))
        print ''
        print 'Candidates'
        print candidates[0]
        print candidates[1]
        print EI
        #print 'optimizing candidates'
        candidates_opt = self.GP_EI_optimize(
                IdxsValsList.fromflattened(candidates))
        EI_opt = self.GP_EI(candidates_opt)
        print ''
        print 'Optimized candidates'
        print candidates_opt[0].idxs
        print candidates_opt[0].vals
        print EI_opt

        num = len(candidates_opt)

        if self.show:

            plt.scatter(x_all[0].vals,
                    y_all * self._GP_y_std + self._GP_y_mean)
            plt.scatter(candidates[1], numpy.zeros_like(candidates[1]),
                c='y')
            plt.scatter(candidates_opt[0].vals,
                    numpy.zeros_like(candidates[1]) - .1,
                    c='k')


            plt.figure()

            plt.xlim([self.xlim_low, self.xlim_high])
            xmesh = numpy.linspace(self.xlim_low, self.xlim_high)
            N = len(xmesh)
            XmeshN = [numpy.arange(N) for _ind in range(num)]
            Xmesh = [numpy.linspace(self.xlim_low, self.xlim_high)
                    for _ind in range(num)]

            print Xmesh

            IVL = IdxsValsList.fromlists(XmeshN, Xmesh)
            gp_mean, gp_var = self.GP_mean_variance(IVL)
            gp_EI = self.GP_EI(IVL)

            print "GP_VAR", gp_var
            plt.plot(xmesh, gp_mean)
            plt.plot(xmesh, gp_mean + numpy.sqrt(gp_var), c='g')
            plt.plot(xmesh, gp_mean - numpy.sqrt(gp_var), c='g')
            plt.plot(xmesh, gp_EI, c='r')
            plt.show()

        best_idx = numpy.argmax(EI_opt)
        args = []
        for c_opt in candidates_opt:
            args.append([c_opt.idxs[best_idx]])
            args.append([c_opt.vals[best_idx]])
        rval = IdxsValsList.fromflattened(tuple(args))
        return rval


class GaussianBandit(GensonBandit):
    test_str = '{"x":gaussian(0,1)}'

    def __init__(self):
        super(GaussianBandit, self).__init__(source_string=self.test_str)

    @classmethod
    def evaluate(cls, config, ctrl):
        return dict(loss=(config['x'] - 2) ** 2, status='ok')

    @classmethod
    def loss_variance(cls, result, config):
        return .1


class UniformBandit(GensonBandit):
    test_str = '{"x":uniform(0,1)}'

    def __init__(self):
        super(UniformBandit, self).__init__(source_string=self.test_str)

    @classmethod
    def evaluate(cls, config, ctrl):
        return dict(loss=(config['x'] - .5) ** 2, status='ok')

    @classmethod
    def loss_variance(cls, result, config):
        return .01 ** 2


class LognormalBandit(GensonBandit):
    test_str = '{"x":lognormal(0,1)}'

    def __init__(self):
        super(LognormalBandit, self).__init__(source_string=self.test_str)

    @classmethod
    def evaluate(cls, config, ctrl):
        return dict(loss=(config['x'] - 2) ** 2, status='ok')

    @classmethod
    def loss_variance(cls, result, config):
        return .1        


class QLognormalBandit(GensonBandit):
    test_str = '{"x":qlognormal(5,2)}'

    def __init__(self):
        super(QLognormalBandit, self).__init__(source_string=self.test_str)

    @classmethod
    def evaluate(cls, config, ctrl):
        return dict(loss=(config['x'] - 30) ** 2, status='ok')

    @classmethod
    def loss_variance(cls, result, config):
        return .1  


class GaussianBandit2var(GensonBandit):
    test_str = '{"x":gaussian(0,1), "y":gaussian(0,1)}'

    def __init__(self, a, b):
        super(GaussianBandit2var, self).__init__(source_string=self.test_str)
        GaussianBandit2var.a = a
        GaussianBandit2var.b = b
    @classmethod
    def evaluate(cls, config, ctrl):
        return dict(loss=cls.a * (config['x'] - 2) ** 2 + \
                                   cls.b * (config['y'] - 2) ** 2, status='ok')

    @classmethod
    def loss_variance(cls, result, config):
        return .1


def fit_base(A, B, *args, **kwargs):

    algo = A(B(*args, **kwargs))
    algo.n_startup_jobs = 7

    n_iter = kwargs.pop('n_iter', 40)
    serial_exp = SerialExperiment(algo)
    serial_exp.run(algo.n_startup_jobs)

    assert len(serial_exp.trials) == len(serial_exp.results)
    assert len(serial_exp.trials) == algo.n_startup_jobs

    def run_then_show(N):
        if N > 1:
            algo.show = False
            algo.use_base_suggest = True
            serial_exp.run(N - 1)
        algo.show = True
        algo.use_base_suggest = False
        serial_exp.run(1)
        return serial_exp

    return run_then_show(n_iter)


def test_fit_normal():
    fit_base(GPAlgo, GaussianBandit)


def test_2var_equal():
    se = fit_base(GPAlgo, GaussianBandit2var, 1, 1)
    l0 = se.bandit_algo.kernels[0].log_lenscale.get_value()
    l1 = se.bandit_algo.kernels[1].log_lenscale.get_value()
    assert .85 < l0 / l1 < 1.15


def test_2var_unequal():
    se = fit_base(GPAlgo, GaussianBandit2var, 1, 0)
    l0 = se.bandit_algo.kernels[0].log_lenscale.get_value()
    l1 = se.bandit_algo.kernels[1].log_lenscale.get_value()
    #N.B. a ratio in log-length scales is a big difference!
    assert l1 / l0 > 5


class GaussianBandit4var(GensonBandit):
    """
    This bandit allows testing continuous distributions nested inside choice
    variables.

    The loss actually only depends on 'a' or 'd'. So the length scales of 'b'
    and 'd' should go to infinity.
    """
    test_str = """{"p0":choice([{"a":gaussian(0,1),"b":gaussian(0,1)},
                                 {"c":gaussian(0,1),"d":gaussian(0,1)}])}"""

    def __init__(self, a, b, c, d):
        super(GaussianBandit4var, self).__init__(source_string=self.test_str)

        # relevances to loss function:
        self.a = a
        self.b = b
        self.c = c
        self.d = d

    def evaluate(self, config, ctrl):
        return dict(loss=self.a * (config['p0'].get("a", 2) - 2) ** 2 + \
                         self.b * (config['p0'].get("b", 2) - 2) ** 2 + \
                         self.c * (config['p0'].get("c", 2) - 2) ** 2 + \
                         self.d * (config['p0'].get("d", 2) - 2) ** 2 ,
                    status='ok')

    def loss_variance(self, result, config):
        """Return uncertainty in reported loss.

        The function is technically deterministic (var = 0), but
        overestimating is ok.
        """
        return .1


def test_4var_all_relevant():
    bandit_algo = GPAlgo(GaussianBandit4var(1, .5, 2, 1))
    serial_exp = SerialExperiment(bandit_algo)
    bandit_algo.n_startup_jobs = 10
    for i in range(50):
        serial_exp.run(1)
    l0 = bandit_algo.kernels[0].log_lenscale.get_value()
    l1 = bandit_algo.kernels[1].log_lenscale.get_value()
    l2 = bandit_algo.kernels[2].log_lenscale.get_value()
    l3 = bandit_algo.kernels[3].log_lenscale.get_value()
    l4 = bandit_algo.kernels[4].log_lenscale.get_value()
    for k in bandit_algo.kernels:
        print 'last kernel fit', k, k.lenscale()
    assert min(serial_exp.losses()) < .05
    hyperopt.plotting.main_plot_vars(serial_exp, end_with_show=True)


def test_4var_some_irrelevant():
    bandit_algo = GPAlgo(GaussianBandit4var(1, 0, 0, 1))
    serial_exp = SerialExperiment(bandit_algo)
    bandit_algo.n_startup_jobs = 10
    for i in range(50):
        serial_exp.run(1)
    l0 = bandit_algo.kernels[0].log_lenscale.get_value()
    l1 = bandit_algo.kernels[1].log_lenscale.get_value()
    l2 = bandit_algo.kernels[2].log_lenscale.get_value()
    l3 = bandit_algo.kernels[3].log_lenscale.get_value()
    l4 = bandit_algo.kernels[4].log_lenscale.get_value()
    for k in bandit_algo.kernels:
        print 'last kernel fit', k, k.lenscale()
    assert min(serial_exp.losses()) < .05
    hyperopt.plotting.main_plot_vars(serial_exp, end_with_show=True)


def test_fit_categorical():
    numpy.random.seed(555)
    serial_exp = SerialExperiment(GPAlgo(TwoArms()))
    serial_exp.bandit_algo.n_startup_jobs = 7
    serial_exp.run(100)
    arm0count = len([t for t in serial_exp.trials if t['x'] == 0])
    arm1count = len([t for t in serial_exp.trials if t['x'] == 1])
    print 'arm 0 count', arm0count
    print 'arm 1 count', arm1count
    # this is just a test of the gm_algo candidate proposal mechanism
    # since the GP doesn't apply to discrete variables.
    assert arm0count > 60


def test_fit_uniform():
    bandit = UniformBandit()
    bandit_algo = GPAlgo(bandit)
    bandit_algo.n_startup_jobs = 5
    serial_exp = SerialExperiment(bandit_algo)
    serial_exp.run(bandit_algo.n_startup_jobs)
    bandit_algo.xlim_low = 0.0   #XXX match UniformBandit
    bandit_algo.xlim_high = 1.0   #XXX match UniformBandit

    k = bandit_algo.kernels[0]
    assert bandit_algo.is_refinable[k]
    assert bandit_algo.bounds[k] == (0, 1)
    bandit_algo.show = False
    bandit_algo.use_base_suggest = True
    serial_exp.run(15)

    assert min(serial_exp.losses()) < .005
    assert bandit_algo.kernels[0].lenscale() < .25

    assert min([t['x'] for t in serial_exp.trials]) >= 0
    assert min([t['x'] for t in serial_exp.trials]) <= 1


def test_fit_lognormal():
    bandit = LognormalBandit()
    bandit_algo = GPAlgo(bandit)
    bandit_algo.n_startup_jobs = 5
    serial_exp = SerialExperiment(bandit_algo)
    serial_exp.run(bandit_algo.n_startup_jobs)
    bandit_algo.xlim_low = 0.001
    bandit_algo.xlim_high = 10.0

    k = bandit_algo.kernels[0]
    assert bandit_algo.is_refinable[k]
    assert bandit_algo.bounds[k][0] > 0
    bandit_algo.show = False
    bandit_algo.use_base_suggest = True
    serial_exp.run(25)

    if 1:
        bandit_algo.use_base_suggest = False
        bandit_algo.show = True
        serial_exp.run(1)

    assert min(serial_exp.losses()) < .005
    assert bandit_algo.kernels[0].lenscale() < .25

    assert min([t['x'] for t in serial_exp.trials]) >= 0
    assert min([t['x'] for t in serial_exp.trials]) <= 1


def test_fit_quantized_lognormal():
    bandit = QLognormalBandit()
    bandit_algo = GPAlgo(bandit)
    bandit_algo.n_startup_jobs = 5
    serial_exp = SerialExperiment(bandit_algo)
    serial_exp.run(bandit_algo.n_startup_jobs)
    bandit_algo.xlim_low = 0.1
    bandit_algo.xlim_high = 300.0

    k = bandit_algo.kernels[0]
    assert bandit_algo.is_refinable[k]
    assert bandit_algo.bounds[k][0] > 0
    bandit_algo.show = False
    bandit_algo.use_base_suggest = True
    serial_exp.run(15)

    if 1:
        bandit_algo.use_base_suggest = False
        bandit_algo.show = True
        serial_exp.run(1)

    assert min(serial_exp.losses()) < .005
    assert bandit_algo.kernels[0].lenscale() < .25

    assert min([t['x'] for t in serial_exp.trials]) >= 0
    assert min([t['x'] for t in serial_exp.trials]) <= 1

def test_fit_dummy_dbn():
    bandit = Dummy_DBN_Base()
    bandit_algo = GPAlgo(bandit)
    bandit_algo.n_startup_jobs = 20
    serial_exp = SerialExperiment(bandit_algo)
    bandit_algo.show = False
    bandit_algo.use_base_suggest = True

    serial_exp.run(bandit_algo.n_startup_jobs)
    serial_exp.run(50) # use the GP for some iterations

    # No assertion here.
    # If it runs this far, it's already something.
