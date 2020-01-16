import logging
import networkx as nx
import numpy as np
import yaml

from geopy.distance import vincenty
from bjointsp.fixed.fixed_instance import FixedInstance
from bjointsp.fixed.source import Source
from bjointsp.heuristic import shortest_paths as sp
from bjointsp.network.links import Links
from bjointsp.network.nodes import Nodes
from bjointsp.overlay.edge import Edge
from bjointsp.overlay.flow import Flow
from bjointsp.overlay.instance import Instance
from bjointsp.overlay.overlay import Overlay
from bjointsp.template.arc import Arc
from bjointsp.template.component import Component
from bjointsp.template.template import Template

logger = logging.getLogger('bjointsp')


# remove empty values (from multiple delimiters in a row)
def remove_empty_values(line):
    result = []
    for i in range(len(line)):
        if line[i] != "":
            result.append(line[i])
    return result


# check all stateful components, set non-bidirectional components to non-stateful (required for constraints)
def update_stateful(template):
    for j in template.components:
        if j.stateful:
            used_forward = False
            used_backward = False
            for a in template.arcs:
                if a.direction == "forward" and a.source == j:
                    used_forward = True  # 1+ outgoing arc at j in forward direction
                if a.direction == "backward" and a.dest == j:
                    used_backward = True  # 1+ incoming arc at j in backward direction

            # if not used in both directions, set to non-stateful
            if not (used_forward and used_backward):
                # print("Stateful component {} is not used bidirectionally and is set to non-stateful.".format(j))
                j.stateful = False


# same as read_network but use an already existing, annotated NetworkX object
# this is highly tailored to the NetworkX objects created by https://github.com/RealVNF/coordination-simulation
def read_networkx(networkx):
    # read nodes: use same cap for cpu and mem (no distinction in the simulator)
    node_ids = [v for v in networkx.nodes.keys()]
    node_cpu = {v[0]: v[1]['cap'] for v in networkx.nodes.data()}
    nodes = Nodes(node_ids, node_cpu, node_cpu.copy())

    # read edges
    link_ids = [e for e in networkx.edges.keys()]
    link_dr = {(e[0], e[1]): e[2]['cap'] for e in networkx.edges.data()}
    link_delay = {(e[0], e[1]): e[2]['delay'] for e in networkx.edges.data()}

    # add reversed links for bidirectionality
    for e in networkx.edges:
        e_reversed = (e[1], e[0])
        link_ids.append(e_reversed)
        link_dr[e_reversed] = link_dr[e]
        link_delay[e_reversed] = link_delay[e]

    links = Links(link_ids, link_dr, link_delay)

    return nodes, links


# read substrate network from graphml-file using NetworkX, set specified node and link capacities
# IMPORTANT: for consistency with emulator, all node IDs are prefixed with "pop" *
# *and have to be referenced as such (eg, in source locations)
def read_network(file, cpu=None, mem=None, dr=None):
    SPEED_OF_LIGHT = 299792458  # meter per second
    PROPAGATION_FACTOR = 0.77  # https://en.wikipedia.org/wiki/Propagation_delay

    if not file.endswith(".graphml"):
        raise ValueError("{} is not a GraphML file".format(file))
    network = nx.read_graphml(file, node_type=int)

    # set nodes
    node_ids = ["pop{}".format(n) for n in network.nodes]  # add "pop" to node index (eg, 1 --> pop1)
    # if specified, use the provided uniform node capacities
    if cpu is not None and mem is not None:
        node_cpu = {"pop{}".format(n): cpu for n in network.nodes}
        node_mem = {"pop{}".format(n): mem for n in network.nodes}
    # else try to read them from the the node attributes (ie, graphml)
    else:
        cpu = nx.get_node_attributes(network, 'cpu')
        mem = nx.get_node_attributes(network, 'mem')
        try:
            node_cpu = {"pop{}".format(n): cpu[n] for n in network.nodes}
            node_mem = {"pop{}".format(n): mem[n] for n in network.nodes}
        except KeyError:
            raise ValueError("No CPU or mem. specified for {} (as cmd argument or in graphml)".format(file))

    # set links
    link_ids = [("pop{}".format(e[0]), "pop{}".format(e[1])) for e in network.edges]
    if dr is not None:
        link_dr = {("pop{}".format(e[0]), "pop{}".format(e[1])): dr for e in network.edges}
    else:
        dr = nx.get_edge_attributes(network, 'dr')
        try:
            link_dr = {("pop{}".format(e[0]), "pop{}".format(e[1])): dr[e] for e in network.edges}
        except KeyError:
            raise ValueError("No link data rate specified for {} (as cmd argument or in graphml)".format(file))

    # calculate link delay based on geo positions of nodes; duplicate links for bidirectionality
    link_delay = {}
    for e in network.edges(data=True):
        delay = 0
        if e[2].get("LinkDelay"):
            delay = e[2]['LinkDelay']
        else:
            n1 = network.nodes(data=True)[e[0]]
            n2 = network.nodes(data=True)[e[1]]
            n1_lat, n1_long = n1.get("Latitude"), n1.get("Longitude")
            n2_lat, n2_long = n2.get("Latitude"), n2.get("Longitude")
            distance = vincenty((n1_lat, n1_long), (n2_lat, n2_long)).meters  # in meters
            delay = (distance / SPEED_OF_LIGHT * 1000) * PROPAGATION_FACTOR  # in milliseconds
        # round delay to int using np.around for consistency with emulator
        link_delay[("pop{}".format(e[0]), "pop{}".format(e[1]))] = int(np.around(delay))

    # add reversed links for bidirectionality
    for e in network.edges:
        e = ("pop{}".format(e[0]), "pop{}".format(e[1]))
        e_reversed = (e[1], e[0])
        link_ids.append(e_reversed)
        link_dr[e_reversed] = link_dr[e]
        link_delay[e_reversed] = link_delay[e]

    nodes = Nodes(node_ids, node_cpu, node_mem)
    links = Links(link_ids, link_dr, link_delay)
    return nodes, links


# read template from yaml file
def read_template(file, return_src_components=False):
    components, arcs = [], []
    with open(file, "r") as template_file:
        template = yaml.load(template_file, yaml.SafeLoader)
        for vnf in template["vnfs"]:
            inputs = (vnf["inputs_fwd"], vnf["inputs_bwd"])
            outputs = (vnf["outputs_fwd"], vnf["outputs_bwd"])
            outgoing = (vnf["out_fwd"], vnf["out_bwd"])
            # Try to retrieve the image if it's in the template
            vnf_image = vnf.get("image", None)
            # Getting the VNF delay from YAML, checking to see if key exists, otherwise set default 0
            vnf_delay = vnf.get("vnf_delay", 0)
            # Check whether vnf is source and has cpu and mem requirements.
            if (vnf["type"] == "source") and (
                    (len(vnf["cpu"]) == 1 and (vnf["cpu"][0] > 0)) or (len(vnf["mem"]) == 1 and (vnf["mem"][0] > 0))):
                logger.info("\tSource component {} has CPU:{} and MEM:{} requirements."
                            " Check the template file".format(vnf['name'], vnf['cpu'], vnf['mem']))
                # print ("Source component {} has CPU:{} and MEM:{} requirements.
                #         Check the template file".format(vnf['name'], vnf['cpu'], vnf['mem']))
            component = Component(vnf["name"], vnf["type"], vnf["stateful"], inputs,
                                  outputs, vnf["cpu"], vnf["mem"], outgoing, vnf_delay, config=vnf_image)
            components.append(component)

        for arc in template["vlinks"]:
            source = list(filter(lambda x: x.name == arc["src"], components))[0]  # get component with specified name
            dest = list(filter(lambda x: x.name == arc["dest"], components))[0]
            arc = Arc(arc["direction"], source, arc["src_output"], dest, arc["dest_input"], arc["max_delay"])
            arcs.append(arc)

    template = Template(template["name"], components, arcs)
    update_stateful(template)

    if return_src_components:
        source_components = {j for j in components if j.source}
        return template, source_components

    return template


# read sources from yaml file
def read_sources(file, source_components):
    sources = []
    with open(file, "r") as sources_file:
        yaml_file = yaml.load(sources_file, yaml.Loader)

        # special case: no sources
        if yaml_file is None:
            return sources

        for src in yaml_file:
            # get the component with the specified name: first (and only) element with source name
            try:
                component = list(filter(lambda x: x.name == src["vnf"], source_components))[0]
                if not component.source:
                    raise ValueError("Component {} is not a source component (required).".format(component))
            except IndexError:
                raise ValueError("Component {} of source unknown (not used in any template).".format(src["vnf"]))

            # read flows
            flows = []
            for f in src["flows"]:
                flows.append(Flow(f["id"], f["data_rate"]))  # explicit float cast necessary for dr?

            sources.append(Source(src["node"], component, flows))
    return sources


# read fixed instances from yaml file
def read_fixed_instances(file, components):
    fixed_instances = []
    with open(file, "r") as stream:
        fixed = yaml.load(stream)
        for i in fixed:
            # get the component with the specified name: first (and only) element with component name
            try:
                component = list(filter(lambda x: x.name == i["vnf"], components))[0]
                if component.source:
                    raise ValueError("Component {} is a source component (forbidden).".format(component))
            except IndexError:
                raise ValueError("Component {} of fixed instance unknown (not used in any template).".format(i["vnf"]))

            fixed_instances.append(FixedInstance(i["node"], component))
    return fixed_instances


# find and return component that matches the VNF name in the specified template. if not there, return None
def get_component(template, name):
    if name in [c.name for c in template.components]:
        component = list(filter(lambda x: x.name == name, template.components))[0]
        return component
    return None


# read previous placement from given networkx object
# highly tailored to NetworkX objects created by https://github.com/RealVNF/coordination-simulation
def read_prev_placement(networkx, templates):
    # create empty overlays for all templates
    prev_embedding = {}  # dict: template -> overlay
    for t in templates:
        prev_embedding[t] = Overlay(t, [], [])

    # only read and recreate placement (not edges or flows)
    for v in networkx.nodes.data():
        node_id = v[0]
        node_attr = v[1]
        for vnf in node_attr['available_sf']:
            # find component that matches the VNF name (in any of the templates)
            for t in templates:
                # use first matching component (assuming it's only in one template); here, "vnf" is the vnf's name
                component = get_component(t, vnf)
                if component is not None:
                    # add new instance to overlay of corresponding template (source components need src_flows being set)
                    if component.source:
                        prev_embedding[t].instances.append(Instance(component, node_id, src_flows=[]))
                    else:
                        prev_embedding[t].instances.append(Instance(component, node_id))
                    break

    return prev_embedding


# read previous embedding from yaml file
def read_prev_embedding(file, templates, nodes, links):
    # create shortest paths
    shortest_paths = sp.all_pairs_shortest_paths(nodes, links)
    # create empty overlays for all templates
    prev_embedding = {}  # dict: template -> overlay
    for t in templates:
        prev_embedding[t] = Overlay(t, [], [])

    with open(file, "r") as f:
        yaml_file = yaml.load(f, yaml.SafeLoader)

        # read and create VNF instances of previous embedding
        for vnf in yaml_file["placement"]["vnfs"]:
            # find component that matches the VNF name (in any of the templates)
            for t in templates:
                # use first matching component (assuming it's only in one template)
                component = get_component(t, vnf["name"])
                if component is not None:
                    # add new instance to overlay of corresponding template (source components need src_flows being set)
                    if component.source:
                        prev_embedding[t].instances.append(Instance(component, vnf["node"], src_flows=[]))
                    else:
                        prev_embedding[t].instances.append(Instance(component, vnf["node"]))
                    break

        # TODO: read and create flows. otherwise, adding edges really doesn't make a difference in the heuristic
        # read and create edges of previous embedding
        for edge in yaml_file["placement"]["vlinks"]:
            instances = [i for ol in prev_embedding.values() for i in ol.instances]

            # try to get source and dest instance from list of instances
            try:
                source = list(filter(lambda x: x.component.name == edge["src_vnf"] and x.location == edge["src_node"],
                                     instances))[0]
                dest = list(filter(lambda x: x.component.name == edge["dest_vnf"] and x.location == edge["dest_node"],
                                   instances))[0]
            # if the vnfs don't exist in prev_embedding (eg, through incorrect input), ignore the edge
            except IndexError:
                # print("No matching VNFs in prev_embedding for edge from {} to {}.
                #                                         Ignoring the edge.".format(source, dest))
                continue  # skip and continue with next edge

            # get arc from templates by matching against source and dest components
            for t in templates:
                if source.component in t.components and dest.component in t.components:
                    # assume t has an arc source->dest if both components are in t
                    arc = list(filter(lambda x: x.source == source.component and x.dest == dest.component, t.arcs))[0]
                    # add new edge to overlay of corresponding template
                    edge = Edge(arc, source, dest)
                    prev_embedding[t].edges.append(edge)
                    edge.paths.append(shortest_paths[(source.location, dest.location)][0])

    return prev_embedding
