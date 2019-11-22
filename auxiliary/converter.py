from math import radians, cos, sin, asin, sqrt
import xml.etree.ElementTree as ET
import csv
import random


# assign cpu/mem resources to nodes randomly uniformly
def node_capacities(nodes, total_node_cap):
	# initialize node capacities to 0
	node_cpu, node_mem = {}, {}
	for v in nodes:
		node_cpu[v] = 0
		node_mem[v] = 0

	# assign chunks of 5 cpu/mem to the nodes randomly uniformly with the specified total capacity
	while total_node_cap > 0:
		total_node_cap -= 5
		v = random.choice(nodes)
		node_cpu[v] += 5
		node_mem[v] += 5

	return node_cpu, node_mem


# calculate distance between two GPS coordinates using the Haversine Formula
# http://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
def distance(lon1, lat1, lon2, lat2):
	# convert decimal degrees to radians
	lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

	# haversine formula
	dlon = lon2 - lon1
	dlat = lat2 - lat1
	a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
	c = 2 * asin(sqrt(a))
	R = 6371        # Radius of earth in kilometers
	return c * R


# rounded propagation delay (in ms) for a given distance (in km) based on propagation speed in fibre (0.67 * c)
def propagation_delay(distance):
	SPEED_OF_LIGHT = 229.792        # in km/ms
	delay = distance / (0.67 * SPEED_OF_LIGHT)
	return round(delay, 2)


# convert xml network from SNDlib to csv format
# node_cap is either the uniform cap per node or the total node cap to be distributed randomly (def. by uniform_node_cap)
def format_sndlib(in_file, node_cap, link_cap, uniform_node_cap, seed=None):
	# create out_file name based on in_file name, capacities, and random seed
	out_file = in_file[:-4]  # strip off .xml-ending
	if uniform_node_cap:
		out_file += "_{}_{}.csv".format(node_cap, link_cap)
	else:
		out_file += "_{}_{}_{}.csv".format(node_cap, link_cap, seed)
	print("Formatting file {} to {}".format(in_file, out_file))

	# save GPS coordinates of all nodes in a dictionary; use to calculate link length later
	coordinates = {}

	prefix = "{http://sndlib.zib.de/network}"     # SNDlib's default prefix
	tree = ET.parse(in_file)

	# collect all node ids
	nodes = []
	for node in tree.iter(prefix + "node"):
		node_id = node.get("id")
		nodes.append(node_id)

	# assign node capacities (uniform or randomly)
	if uniform_node_cap:
		node_cpu, node_mem = {}, {}
		for v in nodes:
			node_cpu[v] = node_cap
			node_mem[v] = node_cap
	else:
		node_cpu, node_mem = node_capacities(nodes, node_cap)

	with open(out_file, "w", newline="") as csvfile:
		writer = csv.writer(csvfile, delimiter=" ")

		writer.writerow(("#", "formatted", "substrate", "network", in_file))

		writer.writerow(("#", "Nodes:", "id", "cpu", "mem"))
		for node in tree.iter(prefix + "node"):
			node_id = node.get("id")
			writer.writerow((node_id, node_cpu[node_id], node_mem[node_id]))
			# save x and y coordinate as tuple (longitude and latitude in decimal degrees, respectively)
			coordinates[node_id] = (float(node[0][0].text), float(node[0][1].text))
		writer.writerow("")

		writer.writerow(("#", "DIRECTED", "Links:", "src_id", "sink_id", "cap", "delay"))
		for link in tree.iter(prefix + "link"):
			source = link.find(prefix + "source").text
			target = link.find(prefix + "target").text
			source_coord = coordinates[source]
			target_coord = coordinates[target]
			link_length = distance(source_coord[0], source_coord[1], target_coord[0], target_coord[1])
			link_delay = propagation_delay(link_length)
			writer.writerow((source, target, link_cap, link_delay))
			writer.writerow((target, source, link_cap, link_delay))        # add backward link


# convert substrate network(s); use paths relative to the location of converter.py (Optimization/read_write/)
seed = 1234
random.seed(seed)           # seed set here, then only passed for setting the file-name
total_node_cap = 100        # distributed among nodes randomly
node_cap = 10				# constant node capacity
uniform_node_cap = True		# toggle between uniform or random node capacities
link_cap = 10               # constant for each link
file = "../Data/brain/brain.xml"

if uniform_node_cap:
	print("Uniform node cap: {}, link cap: {}".format(node_cap, link_cap))
	format_sndlib(file, node_cap, link_cap, uniform_node_cap)
else:
	print("Random node cap: Seed: {}, total node cap: {}, link cap: {}".format(seed, total_node_cap, link_cap))
	format_sndlib(file, total_node_cap, link_cap, uniform_node_cap, seed)