# B-JointSP 

**Note: This branch is for ongoing development for another project. It's not thoroughly tested and may be unstable. For the NetSoft'18 submission, please only consider the master branch. This branch only includes the heuristic, not the MIP.**

B-JointSP is an optimization problem focusing on the joint scaling and placement (called embedding) of NFV network services, consisting of interconnected virtual network functions (VNFs). The exceptional about B-JointSP is its consideration of realistic, bidirectional network services, in which flows return to their sources. It even supports stateful VNFs, that need to be traversed by the same flows in both upstream and downstream direction. Furthermore, B-JointSP allows the reuse of VNFs across different network services and supports physical network functions.


## Setup

```
sudo python3 setup.py develop
```

For some reason, `install` doesn't work...


## Usage

Type `bjointsp -h` for usage help. This should print:

```
usage: bjointsp [-h] -n NETWORK -t TEMPLATE -s SOURCES [-f FIXED]

B-JointSP heuristic calculates an optimized placement

optional arguments:
  -h, --help            show this help message and exit
  -n NETWORK, --network NETWORK
                        Network input file (.graphml)
  -t TEMPLATE, --template TEMPLATE
                        Template input file (.yaml)
  -s SOURCES, --sources SOURCES
                        Sources input file (.yaml)
  -f FIXED, --fixed FIXED
                        Fixed instances input file (.yaml)
```

As an example, you can try running the following command from the source root folder (were README.md is located):

```
bjointsp -n src/bjointsp/parameters/networks/Abilene.graphml -t src/bjointsp/parameters/templates/fw1chain.yaml -s src/bjointsp/parameters/sources/source0.yaml
```

This should start the heuristic and create a result in the `results/bjointsp` directory in form of a yaml file.
