import csv
import networkx as nx
import yaml
from geopy.distance import vincenty
from bjointsp.fixed.fixed_instance import FixedInstance
from bjointsp.fixed.source import Source
from bjointsp.network.links import Links
from bjointsp.network.nodes import Nodes
from bjointsp.overlay.flow import Flow
from bjointsp.template.arc import Arc
from bjointsp.template.component import Component
from bjointsp.template.template import Template


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
					used_forward = True			# 1+ outgoing arc at j in forward direction
				if a.direction == "backward" and a.dest == j:
					used_backward = True		# 1+ incoming arc at j in backward direction

			# if not used in both directions, set to non-stateful
			if not (used_forward and used_backward):
				print("Stateful component {} is not used bidirectionally and is set to non-stateful.".format(j))
				j.stateful = False


# read substrate network from csv-file
def read_network(file):
	node_ids, node_cpu, node_mem = [], {}, {}
	link_ids, link_dr, link_delay = [], {}, {}
	with open(file, "r") as network_file:
		reader = csv.reader((row for row in network_file if not row.startswith("#")), delimiter=" ")
		for row in reader:
			row = remove_empty_values(row)  # deal with multiple spaces in a row leading to empty values

			if len(row) == 3:  # nodes: id, cpu, mem
				node_id = row[0]
				node_ids.append(node_id)
				node_cpu[node_id] = float(row[1])
				node_mem[node_id] = float(row[2])

			if len(row) == 4:  # arcs: src_id, sink_id, cap, delay
				ids = (row[0], row[1])
				link_ids.append(ids)
				link_dr[ids] = float(row[2])
				link_delay[ids] = float(row[3])

	nodes = Nodes(node_ids, node_cpu, node_mem)
	links = Links(link_ids, link_dr, link_delay)
	return nodes, links


# read substrate network from csv-file, set specified node and link capacities
# IMPORTANT: for consistency with emulator, all node IDs are prefixed with "pop" and have to be referenced as such (eg, in source locations)
def read_graphml_network(file, cpu, mem, dr):
	SPEED_OF_LIGHT = 299792458  # meter per second
	PROPAGATION_FACTOR = 0.77  	# https://en.wikipedia.org/wiki/Propagation_delay

	if not file.endswith(".graphml"):
		raise ValueError("{} is not a GraphML file".format(file))
	network = nx.read_graphml(file, node_type=int)
	# set nodes (uniform capacities as specified)
	node_ids = ["pop{}".format(n) for n in network.nodes]		# add "pop" to node index (eg, 1 --> pop1)
	node_cpu = {"pop{}".format(n): cpu for n in network.nodes}
	node_mem = {"pop{}".format(n): mem for n in network.nodes}

	link_ids = [("pop{}".format(e[0]), "pop{}".format(e[1])) for e in network.edges]
	link_dr = {("pop{}".format(e[0]), "pop{}".format(e[1])): dr for e in network.edges}

	# calculate link delay based on geo positions of nodes; duplicate links for bidirectionality
	link_delay = {}
	for e in network.edges:
		n1 = network.nodes(data=True)[e[0]]
		n2 = network.nodes(data=True)[e[1]]
		n1_lat, n1_long = n1.get("Latitude"), n1.get("Longitude")
		n2_lat, n2_long = n2.get("Latitude"), n2.get("Longitude")
		distance = vincenty((n1_lat, n1_long), (n2_lat, n2_long)).meters		# in meters
		delay = (distance / SPEED_OF_LIGHT * 1000) * PROPAGATION_FACTOR  		# in milliseconds
		link_delay[("pop{}".format(e[0]), "pop{}".format(e[1]))] = round(delay)

	# add reversed links for bidirectionality
	for e in network.edges:
		e = ("pop{}".format(e[0]),"pop{}".format(e[1]))
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
		template = yaml.load(template_file)
		for vnf in template["vnfs"]:
			inputs = (vnf["inputs_fwd"], vnf["inputs_bwd"])
			outputs = (vnf["outputs_fwd"], vnf["outputs_bwd"])
			outgoing = (vnf["out_fwd"], vnf["out_bwd"])
			component = Component(vnf["name"], vnf["type"], vnf["stateful"], inputs, outputs, vnf["cpu"], vnf["mem"], outgoing, vnf["image"])
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
		yaml_file = yaml.load(sources_file)
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
				flows.append(Flow(f["id"], f["data_rate"]))		# explicit float cast necessary for dr?

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
