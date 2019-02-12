[![Build Status](https://travis-ci.org/CN-UPB/B-JointSP.svg?branch=master)](https://travis-ci.org/CN-UPB/B-JointSP)

# B-JointSP 

B-JointSP is an optimization problem focusing on the *joint scaling and placemen*t (called embedding) of NFV network services, consisting of interconnected virtual network functions (VNFs). The exceptional about B-JointSP is its consideration of *realistic, bidirectional network services*, in which flows return to their sources. It even supports *stateful VNFs*, that need to be traversed by the same flows in both upstream and downstream direction. Furthermore, B-JointSP allows the reuse of VNFs across different network services and supports physical network functions.

### Cite this work

If you use B-JointSP in your research, please cite our work:

> Sevil Dräxler, Stefan Schneider, Holger Karl: "[Scaling and Placing Bidirectional Services with Stateful Virtual and Physical Network Functions](https://ieeexplore.ieee.org/document/8459915/)". IEEE Conference on Network Softwarization (NetSoft), Montreal, CA (2018)

*Note: For the source code originally implemented and submitted to IEEE NetSoft 2018, refer to the corresponding [release](https://github.com/CN-UPB/B-JointSP/releases/tag/v1.0) or [branch](https://github.com/CN-UPB/B-JointSP/tree/netsoft2018). The master branch contains only the heuristic, not the MIP, and is greatly extended compared to the original code.*

### Changelog

* Feb 2019: Added VNF delays to templates and to calculation of total delay

## Setup

```
python setup.py install
```
Requires Python 3.5+


## Usage

Type `bjointsp -h` for usage help. This should print:

```bash
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
  -p PREV_EMBEDDING, --prev PREV_EMBEDDING
                        Previous embedding input file (.yaml)                     
```

As an example, you can run the following command from the project root folder (where README.md is located):

```bash
bjointsp -n parameters/networks/Abilene.graphml -t parameters/templates/fw1chain.yaml -s parameters/sources/source0.yaml
```

This should start the heuristic and create a result in the `results/bjointsp` directory in form of a yaml file.

## Contact

Lead developer: Stefan Schneider (@StefanUPB)

For questions or support, please use GitHub's issue system.
