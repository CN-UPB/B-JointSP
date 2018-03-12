# reads heuristic results to be used as starting solution
import csv
from bjointsp.overlay.instance import Instance


def read_result(file, components, arcs):
    reading_instances, reading_edges = False, False
    instances, edges = [], []

    with open(file, "r") as sources_file:
        reader = csv.reader((row for row in sources_file), delimiter="\t")
        for row in reader:
            # empty line always means end of a segment
            if len(row) == 0:
                reading_instances = False
                reading_edges = False
                continue

            # start reading instances
            if row[0].startswith("# instances:"):
                reading_instances = True
            elif row[0].startswith("# edges:"):
                reading_edges = True

            # read instances: only set relevant attributes
            if reading_instances and len(row) == 2:
                component = list(filter(lambda x: x.name == row[0], components))[0]
                src_flows = None
                if component.source:
                    src_flows = []
                instances.append(Instance(component, row[1], src_flows))

            # read edges: only set relevant attributes + mapped flows
            if reading_edges and len(row) == 4:
                arc = list(filter(lambda x: str(x) == row[0], arcs))[0]
                # store tuples of (arc, start_node, end_node, flow_id)
                edges.append((arc, row[1], row[2], row[3]))

    return instances, edges