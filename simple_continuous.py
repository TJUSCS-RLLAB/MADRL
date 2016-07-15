#!/usr/bin/env python
#
# File: simple_continuous.py
#
# Created: Thursday, July 14 2016 by rejuvyesh <mail@rejuvyesh.com>
#
from __future__ import absolute_import, print_function

import argparse
import json
import sys
sys.path.append('../rltools/')

import numpy as np
import tensorflow as tf

import gym
import rltools.algos
import rltools.log
import rltools.util
from rltools.sampler import SimpleSampler, ImportanceWeightedSampler, DecSampler
from madrl_environments.pursuit import CentralizedWaterWorld
from rltools.baseline import LinearFeatureBaseline, MLPBaseline, ZeroBaseline
from rltools.gaussian_policy import GaussianMLPPolicy

SIMPLE_POLICY_ARCH = '''[
        {"type": "fc", "n": 128},
        {"type": "nonlin", "func": "tanh"},
        {"type": "fc", "n": 128},
        {"type": "nonlin", "func": "tanh"}
    ]
    '''

SIMPLE_VAL_ARCH = '''[
        {"type": "fc", "n": 128},
        {"type": "nonlin", "func": "tanh"},
        {"type": "fc", "n": 128},
        {"type": "nonlin", "func": "tanh"}
    ]
    '''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--discount', type=float, default=0.95)
    parser.add_argument('--gae_lambda', type=float, default=0.99)

    parser.add_argument('--n_iter', type=int, default=250)
    parser.add_argument('--sampler', type=str, default='simple')
    parser.add_argument('--max_traj_len', type=int, default=200)
    parser.add_argument('--adaptive_batch', action='store_true', default=False)
    parser.add_argument('--batch_size', type=int, default=32)
    parser.add_argument('--min_batch_size', type=int, default=4)
    parser.add_argument('--max_batch_size', type=int, default=64)
    parser.add_argument('--batch_rate', type=int, default=40)
    parser.add_argument('--is_n_backtrack', type=int, default=1)
    parser.add_argument('--is_randomize_draw', action='store_true', default=False)
    parser.add_argument('--is_n_pretrain', type=int, default=0)
    parser.add_argument('--is_skip_is', action='store_true', default=False)
    parser.add_argument('--is_max_is_ratio', type=float, default=0)

    parser.add_argument('--n_evaders', type=int, default=5)
    parser.add_argument('--n_pursuers', type=int, default=3)
    parser.add_argument('--n_poison', type=int, default=10)
    parser.add_argument('--n_coop', type=int, default=2)
    parser.add_argument('--n_sensors', type=int, default=30)

    parser.add_argument('--policy_hidden_spec', type=str, default=SIMPLE_POLICY_ARCH)

    parser.add_argument('--baseline_type', type=str, default='mlp')
    parser.add_argument('--baseline_hidden_spec', type=str, default=SIMPLE_VAL_ARCH)

    parser.add_argument('--max_kl', type=float, default=0.01)
    parser.add_argument('--vf_max_kl', type=float, default=0.01)
    parser.add_argument('--vf_cg_damping', type=float, default=0.01)

    parser.add_argument('--save_freq', type=int, default=20)
    parser.add_argument('--log', type=str, required=False)
    parser.add_argument('--tblog', type=str, default='/tmp/madrl_tb')
    parser.add_argument('--debug', dest='debug', action='store_true')
    parser.add_argument('--no-debug', dest='debug', action='store_false')
    parser.set_defaults(debug=True)

    args = parser.parse_args()

    env = CentralizedWaterWorld(args.n_pursuers, args.n_evaders, args.n_coop, args.n_poison, n_sensors=args.n_sensors)
    policy = GaussianMLPPolicy(env.observation_space, env.action_space, hidden_spec=args.policy_hidden_spec,
                               enable_obsnorm=True,
                               min_stdev=0.,
                               init_logstdev=0.,
                               tblog=args.tblog,
                               varscope_name='gaussmlp_policy')
    if args.baseline_type == 'linear':
        baseline = LinearFeatureBaseline(env.observation_space, enable_obsnorm=True,
                                         varscope_name='pursuit_linear_baseline')
    elif args.baseline_type == 'mlp':
        baseline = MLPBaseline(env.observation_space, args.baseline_hidden_spec,
                               True, True, max_kl=args.vf_max_kl, damping=args.vf_cg_damping,
                               time_scale=1./args.max_traj_len, varscope_name='pursuit_mlp_baseline')
    else:
        baseline = ZeroBaseline(env.observation_space)

    if args.sampler == 'simple':
        sampler_cls = SimpleSampler
        sampler_args = dict(max_traj_len=args.max_traj_len,
                            batch_size=args.batch_size,
                            min_batch_size=args.min_batch_size,
                            max_batch_size=args.max_batch_size,
                            batch_rate=args.batch_rate,
                            adaptive=args.adaptive_batch)
    elif args.sampler == 'imp':
        sampler_cls = ImportanceWeightedSampler
        sampler_args = dict(max_traj_len=args.max_traj_len,
                            batch_size=args.batch_size,
                            min_batch_size=args.min_batch_size,
                            max_batch_size=args.max_batch_size,
                            batch_rate=args.batch_rate,
                            adaptive=args.adaptive_batch,
                            n_backtrack=args.is_n_backtrack,
                            randomize_draw=args.is_randomize_draw,
                            n_pretrain=args.is_n_pretrain,
                            skip_is=args.is_skip_is,
                            max_is_ratio=args.is_max_is_ratio)
    else:
        raise NotImplementedError()
    step_func = rltools.algos.TRPO(max_kl=args.max_kl)
    popt = rltools.algos.SamplingPolicyOptimizer(
        env=env,
        policy=policy,
        baseline=baseline,
        step_func=step_func,
        discount=args.discount,
        gae_lambda=args.gae_lambda,
        sampler_cls=sampler_cls,
        sampler_args=sampler_args,
        n_iter=args.n_iter
    )
    argstr = json.dumps(vars(args), separators=(',', ':'), indent=2)
    rltools.util.header(argstr)
    log_f = rltools.log.TrainingLog(args.log, [('args', argstr)], debug=args.debug)

    with tf.Session() as sess:
        sess.run(tf.initialize_all_variables())
        popt.train(sess, log_f, args.save_freq)


if __name__ == '__main__':
    main()

