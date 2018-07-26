import copy

from bjointsp.overlay.edge import Edge
from bjointsp.overlay.flow import Flow
from bjointsp.overlay.instance import Instance


class Overlay:
    def __init__(self, template, instances, edges):
        self.template = template
        self.instances = instances
        self.edges = edges

    # deepcopy by 1. copying plain instances and flows, 2. adding copies of the edges, 3. mapping new flows to new edges
    def __deepcopy__(self, memodict={}):
        new_overlay = Overlay(self.template, [], [])		# empty overlay
        instance_dict = {}			# dict of old to new instances; for easy access when adding the edges
        flow_dict = {}				# same for old to new flows

        # add new instances with same attributes (component, etc) but without edges_in/out
        for i in self.instances:
            # copy src_flows
            new_src_flows = None
            if i.src_flows:
                new_src_flows = []
                for f in i.src_flows:
                    new_flow = Flow(f.id, f.src_dr)
                    flow_dict[f] = new_flow
                    new_src_flows.append(new_flow)
            # copy instances
            new_instance = Instance(i.component, i.location, new_src_flows, i.fixed)
            new_overlay.instances.append(new_instance)
            instance_dict[i] = new_instance

        # add new edges in topological order => sets edges_in/out etc automatically
        for e in self.topological_order(True):
            # source/dest from new_overlay's instances using the instance_dict
            new_source = instance_dict[e.source]
            new_dest = instance_dict[e.dest]
            # create new edge with references to the new instances and manually set the remaining attributes
            new_edge = Edge(e.arc, new_source, new_dest)
            new_edge.direction = e.direction
            new_edge.paths = copy.deepcopy(e.paths, memodict)		# deepcopy for copying list of lists

            # copy and update flows
            for f in e.flows:
                new_flow = flow_dict[f]
                new_edge.flows.append(new_flow)
                new_flow.dr[new_edge] = f.dr[e]
                if new_edge.source.component.stateful:
                    new_flow.passed_stateful[new_edge.source.component] = new_edge.source
                elif new_edge.dest.component.stateful:
                    new_flow.passed_stateful[new_edge.dest.component] = new_edge.dest

            new_overlay.edges.append(new_edge)

        return new_overlay

    # return whether the overlay is empty, i.e., has no instances and no edges
    def empty(self):
        return not self.instances and not self.edges

    # return topological order of instances or edges (depending on return_edges)
    # add instances consistent to the template's topological component order
    def topological_order(self, return_edges=False):
        instance_order, edge_order = [], []

        direction = "forward"
        end_reached = False			# True when end component was reached
        for j in self.template.topological_component_order():
            # switch direction after last end component
            if j.end:
                end_reached = True
            if end_reached and not j.end:
                direction = "backward"

            # add source instances independent of their ingoing edges
            if j.source:
                curr_instances = [i for i in self.instances if i.component == j]
            # add corresponding instances with ingoing edges in the curr direction or no edges (removed by heuristic)
            else:
                curr_instances = [i for i in self.instances if i.component == j and (i.used(direction, self) or not i.edges_in)]
            instance_order += curr_instances

            # add ingoing edges of current direction to edge_order
            curr_edges = [e for e in self.edges if e.dest in curr_instances and e.direction == direction]
            edge_order += curr_edges

        if return_edges:
            return edge_order
        return instance_order

    def print(self):
        print("Overlay of {}".format(self.template))
        print("\t{} instances:".format(len(self.instances)), *self.instances, sep=" ")
        print("\t{} edges:".format(len(self.edges)), *self.edges, sep=" ")
