import csv
from collections import defaultdict

from gurobipy import *

import bjointsp.template.adapter as adapter
from bjointsp.fixed.fixed_instance import FixedInstance
from bjointsp.fixed.source import Source
from bjointsp.network.links import Links
from bjointsp.network.nodes import Nodes
from bjointsp.overlay.flow import Flow
from bjointsp.template.arc import Arc
from bjointsp.template.component import Component
from bjointsp.template.template import Template


# convert a string (eg., "[1,2]") into a list of float-coefficients (eg., [1.0,2.0])
def coeff_list(string):
	if len(string) == 2:  				# empty list "[]"
		return []
	result = string[1:-1].split(",")  	# remove brackets and split
	result = list(map(float, result))  	# convert to float-list
	return result


# convert string (eg., "[[1,2],[3.5]]" into multiple coeff-lists (eg., [1.0,2.0],[3.5])
def coeff_lists(string):
	if len(string) == 2:  				# empty list "[]"
		return []
	result = []
	strings = string[1:-1].split(";")  	# remove brackets and split
	for item in strings:  				# convert strings to float-lists
		result.append(coeff_list(item))
	return result


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
	link_ids = tuplelist(link_ids)
	links = Links(link_ids, link_dr, link_delay)
	return nodes, links


# read template from csv-file
def read_template(file):
	components, arcs = [], []
	with open(file, "r") as template_file:
		reader = csv.reader((row for row in template_file if not row.startswith("#")), delimiter="\t")
		for row in reader:
			row = remove_empty_values(row)  # deal with multiple tabs in a row leading to empty values

			# template name
			if len(row) == 1:
				name = row[0]

			# components: name, type, stateful, inputs, in_back, outputs, out_back, [cpu_coeff], [mem_coeff],
			# [[outgoing_coeff]], [[outgoing_back]]
			if len(row) == 11:
				if row[1].strip() == "source":
					stateful = True		# source instances always considered stateful
				else:
					stateful = row[2].strip() == "True"
				inputs = (int(row[3]), int(row[4]))
				outputs = (int(row[5]), int(row[6]))
				cpu = coeff_list(row[7])
				mem = coeff_list(row[8])
				outgoing = (coeff_lists(row[9]), coeff_lists(row[10]))
				component = Component(row[0], row[1].strip(), stateful, inputs, outputs, cpu, mem, outgoing)
				components.append(component)

			# arcs: direction, src_name, src_output, dest_name, dest_input, max_delay
			if len(row) == 6:
				source = list(filter(lambda x: x.name == row[1].strip(), components))[0]  # get component with specified name
				dest = list(filter(lambda x: x.name == row[3].strip(), components))[0]
				arc = Arc(row[0].strip(), source, int(row[2]), dest, int(row[4]), float(row[5]))
				arcs.append(arc)

	template = Template(name, components, arcs)
	update_stateful(template)
	return template


# read sources from csv-file
def read_sources(file, source_components):
	sources = []
	with open(file, "r") as sources_file:
		reader = csv.reader((row for row in sources_file if not row.startswith("#")), delimiter=" ")
		for row in reader:
			row = remove_empty_values(row)  # deal with multiple spaces in a row leading to empty values

			if len(row) >= 4 and len(row) % 2 == 0:
				try:
					# get the component with the specified name: first (and only) element with source name
					component = list(filter(lambda x: x.name == row[1], source_components))[0]
					if not component.source:
						raise ValueError("Component {} is not a source component (required).".format(component))
				except IndexError:
					raise ValueError("Component {} of source unknown (not used in any template).".format(row[1]))

				# read flows
				flows = []
				for i in range(2, len(row), 2):
					flows.append(Flow(row[i], float(row[i+1])))

				# source = (nodeID, source component, data rate)
				source = Source(row[0], component, flows)
				sources.append(source)
	return sources


# read fixed instances from csv-file
def read_fixed_instances(file, components):
	fixed_instances = []
	with open(file, "r") as sources_file:
		reader = csv.reader((row for row in sources_file if not row.startswith("#")), delimiter=" ")
		for row in reader:
			row = remove_empty_values(row)  # deal with multiple spaces in a row leading to empty values

			if len(row) == 2:
				try:
					# get the component with the specified name: first (and only) element with component name
					component = list(filter(lambda x: x.name == row[1], components))[0]
					if component.source:
						raise ValueError("Component {} is a source component (forbidden).".format(component))
				except IndexError:
					raise ValueError("Component {} of fixed instance unknown (not used in any template).".format(row[1]))

				# fixed instance = (nodeID, component)
				instance = FixedInstance(row[0], component)
				fixed_instances.append(instance)
	return fixed_instances


# read previous overlay from csv-file (only for MIP)
def read_prev_embedding(file, components):
	# store overlay in a dictionary (component: list of nodes)
	prev_embedding = defaultdict(list)
	with open(file, "r") as embedding_file:
		reader = csv.reader((row for row in embedding_file if not row.startswith("#")))
		for row in reader:
			# row = remove_empty_values(row)  # deal with multiple spaces in a row leading to empty values
			row = row[0].split()

			if len(row) == 2:
				try:
					# get the component with the specified name: first (and only) element with component name
					component = list(filter(lambda x: x.name == row[1], components))[0]
				except IndexError:
					raise ValueError("Component {} of prev overlay unknown (not used in any template).".format(row[1]))

				prev_embedding[component].append(row[0])
	return prev_embedding


# read event from the specified row number of the specified csv-file and return updated input (only for heuristic)
def read_event(file, event_no, templates, sources, fixed):
	directory = os.path.dirname(file)  # directory of the scenario file

	with open(file, "r") as csvfile:
		reader = csv.reader((row for row in csvfile if not row.startswith("#") and len(row) > 1), delimiter=" ")
		# continue reading from file_position
		events = list(reader)
		event_row = events[event_no]
		event_row = remove_empty_values(event_row)  # deal with multiple spaces in a row leading to empty values

		# handle event and update corresponding input
		if event_row[0] == "templates:":
			print("Update templates: {}\n".format(event_row[1:]))
			templates = []
			for template_file in event_row[1:]:					# iterate over all templates, skipping the "templates:"
				path = os.path.join(directory, template_file)
				template = read_template(path)
				templates.append(template)
			templates = adapter.adapt_for_reuse(templates)		# add ports etc on the fly

		elif event_row[0] == "sources:":
			print("Update sources: {}\n".format(event_row[1]))

			# collect source components
			source_components = set()
			for t in templates:
				source_components.update([j for j in t.components if j.source])

			path = os.path.join(directory, event_row[1])
			sources = read_sources(path, source_components)

		elif event_row[0] == "fixed:":
			print("Update fixed instances: {}\n".format(event_row[1]))

			# collect non-source components of used templates
			possible_components = set()
			for template in templates:
				possible_components.update([j for j in template.components if not j.source])
			path = os.path.join(directory, event_row[1])
			fixed = read_fixed_instances(path, possible_components)

		else:
			print("Event not recognized (=> ignore): {}".format(event_row))

		# increment to next row number if it exists; if the last row is reached, set row_no to None
		event_no += 1
		if event_no >= len(events):
			event_no = None

	return event_no, event_row, templates, sources, fixed


# read scenario with all inputs for a problem instance (inputs must be listed and read in the specified order)
# substrate network, templates, previous overlay, sources, fixed instances
def read_scenario(file):
	# initialize inputs as empty (except network, this is always required)
	templates, sources, fixed_instances = [], [], []
	prev_embedding = defaultdict(list)
	events = None

	directory = os.path.dirname(file)							# directory of the scenario file

	with open(file, "r") as csvfile:
		reader = csv.reader((row for row in csvfile if not row.startswith("#")), delimiter=" ")
		for row in reader:
			row = remove_empty_values(row)  # deal with multiple spaces in a row leading to empty values

			if len(row) > 1:									# only consider rows with 1+ file name(s)
				if row[0] == "network:":
					path = os.path.join(directory, row[1])		# look in the same directory as the scenario file
					network = read_network(path)
					nodes = network[0]
					links = network[1]

				elif row[0] == "templates:":
					for template_file in row[1:]:				# iterate over all templates, skipping the "templates:"
						path = os.path.join(directory, template_file)
						template = read_template(path)
						templates.append(template)
					templates = adapter.adapt_for_reuse(templates)		# add ports etc on the fly

				elif row[0] == "sources:":
					# collect source components
					source_components = set()
					for t in templates:
						source_components.update([j for j in t.components if j.source])

					path = os.path.join(directory, row[1])
					sources = read_sources(path, source_components)

				elif row[0] == "fixed:":
					# collect non-source components of used templates
					possible_components = set()
					for template in templates:
						possible_components.update([j for j in template.components if not j.source])
					path = os.path.join(directory, row[1])
					fixed_instances = read_fixed_instances(path, possible_components)

				elif row[0] == "prev_embedding:":
					# collect all components
					components = set()
					for t in templates:
						components.update(t.components)
					path = os.path.join(directory, row[1])
					prev_embedding = read_prev_embedding(path, components)

				elif row[0] == "events:":
					# set path to events-file
					events = os.path.join(directory, row[1])

	return nodes, links, templates, sources, fixed_instances, prev_embedding, events
