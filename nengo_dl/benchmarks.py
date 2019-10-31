"""
Benchmark networks and utilities for evaluating NengoDL's performance.
"""

import inspect
import random
import time

import click
import nengo
import numpy as np
import tensorflow as tf

import nengo_dl
from nengo_dl.compat import tf_compat


def cconv(dimensions, neurons_per_d, neuron_type):
    """
    Circular convolution (EnsembleArray) benchmark.

    Parameters
    ----------
    dimensions : int
        Number of dimensions for vector values
    neurons_per_d : int
        Number of neurons to use per vector dimension
    neuron_type : `~nengo.neurons.NeuronType`
        Simulation neuron type

    Returns
    -------
    net : `nengo.Network`
        benchmark network
    """

    with nengo.Network(label="cconv", seed=0) as net:
        net.config[nengo.Ensemble].neuron_type = neuron_type
        net.config[nengo.Ensemble].gain = nengo.dists.Choice([1, -1])
        net.config[nengo.Ensemble].bias = nengo.dists.Uniform(-1, 1)

        net.cconv = nengo.networks.CircularConvolution(neurons_per_d, dimensions)

        net.inp_a = nengo.Node([0] * dimensions)
        net.inp_b = nengo.Node([1] * dimensions)
        nengo.Connection(net.inp_a, net.cconv.A)
        nengo.Connection(net.inp_b, net.cconv.B)

        net.p = nengo.Probe(net.cconv.output)

    return net


def integrator(dimensions, neurons_per_d, neuron_type):
    """
    Single integrator ensemble benchmark.

    Parameters
    ----------
    dimensions : int
        Number of dimensions for vector values
    neurons_per_d : int
        Number of neurons to use per vector dimension
    neuron_type : `~nengo.neurons.NeuronType`
        Simulation neuron type

    Returns
    -------
    net : `nengo.Network`
        benchmark network
    """

    with nengo.Network(label="integrator", seed=0) as net:
        net.config[nengo.Ensemble].neuron_type = neuron_type
        net.config[nengo.Ensemble].gain = nengo.dists.Choice([1, -1])
        net.config[nengo.Ensemble].bias = nengo.dists.Uniform(-1, 1)

        net.integ = nengo.networks.EnsembleArray(neurons_per_d, dimensions)
        nengo.Connection(net.integ.output, net.integ.input, synapse=0.01)

        net.inp = nengo.Node([0] * dimensions)
        nengo.Connection(net.inp, net.integ.input, transform=0.01)

        net.p = nengo.Probe(net.integ.output)

    return net


def pes(dimensions, neurons_per_d, neuron_type):
    """
    PES learning rule benchmark.

    Parameters
    ----------
    dimensions : int
        Number of dimensions for vector values
    neurons_per_d : int
        Number of neurons to use per vector dimension
    neuron_type : `~nengo.neurons.NeuronType`
        Simulation neuron type

    Returns
    -------
    net : `nengo.Network`
        benchmark network
    """

    with nengo.Network(label="pes", seed=0) as net:
        net.config[nengo.Ensemble].neuron_type = neuron_type
        net.config[nengo.Ensemble].gain = nengo.dists.Choice([1, -1])
        net.config[nengo.Ensemble].bias = nengo.dists.Uniform(-1, 1)

        net.inp = nengo.Node([1] * dimensions)
        net.pre = nengo.Ensemble(neurons_per_d * dimensions, dimensions)
        net.post = nengo.Node(size_in=dimensions)

        nengo.Connection(net.inp, net.pre)

        conn = nengo.Connection(net.pre, net.post, learning_rule_type=nengo.PES())

        nengo.Connection(net.post, conn.learning_rule, transform=-1)
        nengo.Connection(net.inp, conn.learning_rule)

        net.p = nengo.Probe(net.post)

    return net


def basal_ganglia(dimensions, neurons_per_d, neuron_type):
    """
    Basal ganglia network benchmark.

    Parameters
    ----------
    dimensions : int
        Number of dimensions for vector values
    neurons_per_d : int
        Number of neurons to use per vector dimension
    neuron_type : `~nengo.neurons.NeuronType`
        Simulation neuron type

    Returns
    -------
    net : `nengo.Network`
        benchmark network
    """

    with nengo.Network(label="basal_ganglia", seed=0) as net:
        net.config[nengo.Ensemble].neuron_type = neuron_type

        net.inp = nengo.Node([1] * dimensions)
        net.bg = nengo.networks.BasalGanglia(dimensions, neurons_per_d)
        nengo.Connection(net.inp, net.bg.input)
        net.p = nengo.Probe(net.bg.output)

    return net


def mnist(use_tensor_layer=True):
    """
    A network designed to stress-test tensor layers (based on mnist net).

    Parameters
    ----------
    use_tensor_layer : bool
        If True, use individual tensor_layers to build the network, as opposed
        to a single TensorNode containing all layers.

    Returns
    -------
    net : `nengo.Network`
        benchmark network
    """

    with nengo.Network() as net:
        # create node to feed in images
        net.inp = nengo.Node(np.ones(28 * 28))

        if use_tensor_layer:
            nengo_nl = nengo.RectifiedLinear()

            ensemble_params = dict(
                max_rates=nengo.dists.Choice([100]), intercepts=nengo.dists.Choice([0])
            )
            amplitude = 1
            synapse = None

            x = nengo_dl.tensor_layer(
                net.inp,
                tf.keras.layers.Conv2D(filters=32, kernel_size=3),
                shape_in=(28, 28, 1),
            )
            x = nengo_dl.tensor_layer(x, nengo_nl, **ensemble_params)

            x = nengo_dl.tensor_layer(
                x,
                tf.keras.layers.Conv2D(filters=32, kernel_size=3),
                shape_in=(26, 26, 32),
                transform=amplitude,
            )
            x = nengo_dl.tensor_layer(x, nengo_nl, **ensemble_params)

            x = nengo_dl.tensor_layer(
                x,
                tf.keras.layers.AveragePooling2D(pool_size=2, strides=2),
                shape_in=(24, 24, 32),
                synapse=synapse,
                transform=amplitude,
            )

            x = nengo_dl.tensor_layer(x, tf.keras.layers.Dense(units=128))
            x = nengo_dl.tensor_layer(x, nengo_nl, **ensemble_params)

            x = nengo_dl.tensor_layer(
                x, tf.keras.layers.Dropout(rate=0.4), transform=amplitude
            )

            x = nengo_dl.tensor_layer(x, tf.keras.layers.Dense(units=10))
        else:
            nl = tf.nn.relu

            # def softlif_layer(x, sigma=1, tau_ref=0.002, tau_rc=0.02,
            #                   amplitude=1):
            #     # x -= 1
            #     z = tf.nn.softplus(x / sigma) * sigma
            #     z += 1e-10
            #     rates = amplitude / (tau_ref + tau_rc * tf.log1p(1 / z))
            #     return rates

            def mnist_node(x):  # pragma: no cover
                x = tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=nl)(x)
                x = tf.keras.layers.Conv2D(filters=32, kernel_size=3, activation=nl)(x)
                x = tf.keras.layers.AveragePooling2D(pool_size=2, strides=2)(x)
                x = tf.keras.layers.Flatten()(x)
                x = tf.keras.layers.Dense(128, activation=nl)(x)
                x = tf.keras.layers.Dropout(rate=0.4)(x)
                x = tf.keras.layers.Dense(10)(x)

                return x

            node = nengo_dl.TensorNode(
                mnist_node, shape_in=(28, 28, 1), shape_out=(10,)
            )
            x = node
            nengo.Connection(net.inp, node, synapse=None)

        net.p = nengo.Probe(x)

    return net


def spaun(dimensions):
    """
    Builds the Spaun network from [1]_

    Parameters
    ----------
    dimensions : int
        Number of dimensions for vector values

    Returns
    -------
    net : `nengo.Network`
        benchmark network

    References
    ----------
    .. [1] Chris Eliasmith, Terrence C. Stewart, Xuan Choo, Trevor Bekolay,
       Travis DeWolf, Yichuan Tang, and Daniel Rasmussen (2012). A large-scale
       model of the functioning brain. Science, 338:1202-1205.

    Notes
    -----
    This network needs to be installed via

    .. code-block:: bash

        pip install git+https://github.com/drasmuss/spaun2.0.git
    """

    # pylint: disable=import-outside-toplevel
    from _spaun.configurator import cfg
    from _spaun.vocabulator import vocab
    from _spaun.experimenter import experiment
    from _spaun.modules.stim import stim_data
    from _spaun.modules.vision import vis_data
    from _spaun.modules.motor import mtr_data
    from _spaun.spaun_main import Spaun

    vocab.sp_dim = dimensions
    cfg.mtr_arm_type = None

    cfg.set_seed(1)
    experiment.initialize(
        "A",
        stim_data.get_image_ind,
        stim_data.get_image_label,
        cfg.mtr_est_digit_response_time,
        "",
        cfg.rng,
    )
    vocab.initialize(stim_data.stim_SP_labels, experiment.num_learn_actions, cfg.rng)
    vocab.initialize_mtr_vocab(mtr_data.dimensions, mtr_data.sps)
    vocab.initialize_vis_vocab(vis_data.dimensions, vis_data.sps)

    return Spaun()


def random_network(
    dimensions,
    neurons_per_d,
    neuron_type,
    n_ensembles,
    connections_per_ensemble,
    seed=0,
):
    """
    Basal ganglia network benchmark.

    Parameters
    ----------
    dimensions : int
        Number of dimensions for vector values
    neurons_per_d : int
        Number of neurons to use per vector dimension
    neuron_type : `~nengo.neurons.NeuronType`
        Simulation neuron type
    n_ensembles : int
        Number of ensembles in the network
    connections_per_ensemble : int
        Outgoing connections from each ensemble

    Returns
    -------
    net : `nengo.Network`
        benchmark network
    """

    random.seed(seed)
    with nengo.Network(label="random", seed=seed) as net:
        net.inp = nengo.Node([0] * dimensions)
        net.out = nengo.Node(size_in=dimensions)
        net.p = nengo.Probe(net.out)
        ensembles = [
            nengo.Ensemble(
                neurons_per_d * dimensions, dimensions, neuron_type=neuron_type
            )
            for _ in range(n_ensembles)
        ]
        dec = np.ones((neurons_per_d * dimensions, dimensions))
        for ens in net.ensembles:
            # add a connection to input and output node, so we never have
            # any "orphan" ensembles
            nengo.Connection(net.inp, ens)
            nengo.Connection(ens, net.out, solver=nengo.solvers.NoSolver(dec))

            posts = random.sample(ensembles, connections_per_ensemble)
            for post in posts:
                nengo.Connection(ens, post, solver=nengo.solvers.NoSolver(dec))

    return net


def run_profile(
    net, train=False, n_steps=150, do_profile=True, reps=1, dtype="float32", **kwargs
):
    """
    Run profiler on a benchmark network.

    Parameters
    ----------
    net : `~nengo.Network`
        The nengo Network to be profiled.
    train : bool
        If True, profile the ``sim.train`` function. Otherwise, profile the
        ``sim.run`` function.
    n_steps : int
        The number of timesteps to run the simulation.
    do_profile : bool
        Whether or not to run profiling
    reps : int
        Repeat the run this many times (only profile data from the last
        run will be kept).
    dtype : str
        Simulation dtype (e.g. "float32")

    Returns
    -------
    exec_time : float
        Time (in seconds) taken to run the benchmark, taking the minimum over
        ``reps``.

    Notes
    -----
    kwargs will be passed on to `.Simulator`
    """

    exec_time = 1e10
    n_batches = 3 if do_profile else 1

    with net:
        nengo_dl.configure_settings(inference_only=not train, dtype=dtype)

    with nengo_dl.Simulator(net, **kwargs) as sim:
        if do_profile:
            callback = [
                nengo_dl.callbacks.TensorBoard(
                    log_dir="profile", profile_batch=n_batches
                )
            ]
        else:
            callback = None

        if hasattr(net, "inp"):
            x = {
                net.inp: np.random.randn(
                    sim.minibatch_size * n_batches, n_steps, net.inp.size_out
                )
            }
        else:
            x = {
                net.inp_a: np.random.randn(
                    sim.minibatch_size * n_batches, n_steps, net.inp_a.size_out
                ),
                net.inp_b: np.random.randn(
                    sim.minibatch_size * n_batches, n_steps, net.inp_b.size_out
                ),
            }

        if train:
            y = {
                net.p: np.random.randn(
                    sim.minibatch_size * n_batches, n_steps, net.p.size_in
                )
            }

            sim.compile(
                tf_compat.train.GradientDescentOptimizer(0.001), loss=tf.losses.mse
            )

            # run once to eliminate startup overhead
            sim.fit(x, y, epochs=1)

            for _ in range(reps):
                start = time.time()
                sim.fit(x, y, epochs=1, callbacks=callback)
                exec_time = min(time.time() - start, exec_time)
            print("Execution time:", exec_time)

        else:
            # run once to eliminate startup overhead
            sim.predict(x, n_steps=n_steps)

            for _ in range(reps):
                start = time.time()
                sim.predict(x, n_steps=n_steps, callbacks=callback)
                exec_time = min(time.time() - start, exec_time)
            print("Execution time:", exec_time)

    exec_time /= n_batches

    return exec_time


@click.group(chain=True)
def main():
    """Command-line interface for benchmarks."""


@main.command()
@click.pass_obj
@click.option("--benchmark", default="cconv", help="Name of benchmark network")
@click.option("--dimensions", default=128, help="Number of dimensions")
@click.option("--neurons_per_d", default=64, help="Neurons per dimension")
@click.option("--neuron_type", default="RectifiedLinear", help="Nengo neuron model")
@click.option(
    "--kwarg",
    type=str,
    multiple=True,
    help="Arbitrary kwarg to pass to benchmark network (key=value)",
)
def build(obj, benchmark, dimensions, neurons_per_d, neuron_type, kwarg):
    """Builds one of the benchmark networks"""

    # get benchmark network by name
    benchmark = globals()[benchmark]

    # get the neuron type object from string class name
    try:
        neuron_type = getattr(nengo, neuron_type)()
    except AttributeError:
        neuron_type = getattr(nengo_dl, neuron_type)()

    # set up kwargs
    kwargs = dict((k, int(v)) for k, v in [a.split("=") for a in kwarg])

    # add the special cli kwargs if applicable; note we could just do
    # everything through --kwarg, but it is convenient to have a
    # direct option for the common arguments
    params = inspect.signature(benchmark).parameters
    for kw in ("benchmark", "dimensions", "neurons_per_d", "neuron_type"):
        if kw in params:
            kwargs[kw] = locals()[kw]

    # build benchmark and add to context for chaining
    print(
        "Building %s with %s"
        % (nengo_dl.utils.function_name(benchmark, sanitize=False), kwargs)
    )

    obj["net"] = benchmark(**kwargs)


@main.command()
@click.pass_obj
@click.option(
    "--train/--no-train",
    default=False,
    help="Whether to profile training (as opposed to running) the network",
)
@click.option(
    "--n_steps", default=150, help="Number of steps for which to run the simulation"
)
@click.option("--batch_size", default=1, help="Number of inputs to the model")
@click.option(
    "--device",
    default="/gpu:0",
    help="TensorFlow device on which to run the simulation",
)
@click.option(
    "--unroll", default=25, help="Number of steps for which to unroll the simulation"
)
@click.option(
    "--time-only",
    is_flag=True,
    default=False,
    help="Only count total time, rather than profiling internals",
)
def profile(obj, train, n_steps, batch_size, device, unroll, time_only):
    """Runs profiling on a network (call after 'build')"""

    if "net" not in obj:
        raise ValueError("Must call `build` before `profile`")

    obj["time"] = run_profile(
        obj["net"],
        do_profile=not time_only,
        train=train,
        n_steps=n_steps,
        minibatch_size=batch_size,
        device=device,
        unroll_simulation=unroll,
    )


if __name__ == "__main__":
    main(obj={})  # pragma: no cover
