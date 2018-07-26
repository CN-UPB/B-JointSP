# B-JointSP 

B-JointSP is an optimization problem focusing on the *joint scaling and placement* (called embedding) of NFV network services, consisting of interconnected virtual network functions (VNFs). The exceptional about B-JointSP is its consideration of *realistic, bidirectional network services*, in which flows return to their sources. It even supports *stateful VNFs*, that need to be traversed by the same flows in both upstream and downstream direction. Furthermore, B-JointSP allows the reuse of VNFs across different network services and supports physical network functions.

This repository provides the source code for an optimization approach formulated as MIP that can be linearized as MILP and solved with Gurobi. We also provide a fast heuristic algorithm.

*This branch contains the source code belonging to the original implementation of B-JointSP for IEEE NetSoft 2018. It contains both the MIP and the heuristic implementation. The master branch contains updated, easier to use version that only includes the heuristic.*

## Installation requirements

* [Python 3.5](https://www.python.org/)
* [Gurobi 7.0](http://www.gurobi.com/) and [gurobipy](http://www.gurobi.com/documentation/6.5/quickstart_mac/the_gurobi_python_interfac.html) for the optimization approach

*Use the master branch with out the MIP (just heuristic) to avoid the gurobipy dependency and easier installation and usage.*

## Usage/Execution

### Parameters

To describe an embedding scenario, the following parameters are required:

* A substrate network, with node and link capacities as well as link delays
* At least one network service (template), specifying the different kinds of VNFs in the service and their interconnection
* Sources corresponding to the source components of the specified services and located at certain network nodes. Each source specifies at least one outgoing flow (and its flow strength).

Optional parameters:

* Fixed locations of physical network functions
* A previously existing embedding to be optimized

Each of these parameters is described by a separate csv file. A scenario description (also csv) references these individual parameters. See the `parameters` folder for examples.

When running the MIP or the heuristic, the detailed embedding results are stored in `parameters/results` and logs (for debugging or checking the progress) are in `parameters/logs`.

### MIP

To run the MIP and obtain optimal results (with Gurobi), use the following command: `python main.py mip <scenario> (<repetition>)`, where `<scenario>` is the path to a scenario file and `(<repetition>)` is an optional repetition number just for distinguishing different runs with the same parameters.

For example, `python main.py mip parameters/scenarios/simple.csv` solves a simple embedding example, where a bidirectional network service with a firewall and a vCDN is embedded into a four-node network.

### Heuristic

To run the heuristic algorithm, use the command `python main.py heuristic <scenario> (<seed>)`. Again, `<seed>` specifies the scenario file and `(<seed>)` is an optional seed for randomization.

The same example embedding can also be performed with the heuristic: `python main.py heuristic parameters/scenarios/simple.csv`.

## Contact

This source code belongs to the paper "**Scaling and Placing Bidirectional Services with Stateful Virtual and Physical Network Functions**" submitted to IEEE NetSoft 2018 by Sevil Dräxler, Stefan Schneider, and Holger Karl.

Lead developer: Stefan Schneider

For questions or support, please use GitHub's issue system.