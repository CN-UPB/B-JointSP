# module for parsing results in a folder and summarizing them in a single csv-file (just the main metrics)
# only summarize results of heuristic, mip, or pareto (not mixed)
import os.path
import csv
import math
import warnings
import read_write.reader as reader
from collections import defaultdict


# arguments
folder = "../Data/evaluation/mip/west"
scenario = "west"		# name of the scenario; used as prefix of results
# read network to calculate over-subscription based on capacities (only necessary when over-sub isn't minimized)
nodes, links = reader.read_network("../Data/abilene/abilene-west.csv")
# toggle between mip and heuristic
mip = True
# toggle between recalculating over-subscription, necessary when it's not minimized (but always happens for pareto)
calc_over_sub = True
# if mip=True, toggle between pareto (with bounds) or normal (without bounds)
pareto = False
# toggle if files in subdirectories are also read and summarized
check_subdirs = True
# toggle whether just to check correct edge delays (ie, only for existing edges)
only_check_correctness = False


# empty class to store and access results easily as objects with attributes
class Result:
	# set source number and dr to "NA" to avoid errors with results of previous implementations without src_no and src_dr
	def __init__(self):
		self.src_no = "NA"
		self.src_dr = "NA"


# read result file and return values as Result-object
def read_file(file):
	result = Result()
	with open(file, "r") as result_file:
		result.name = file
		for line in result_file:
			# general info
			if line.startswith("source_number"):
				result.src_no = line.split()[1]
			if line.startswith("source_dr"):
				result.src_dr = line.split()[1]
			if line.startswith("Model:"):
				result.model = line.split()[1]
			elif line.startswith("Objective:"):
				result.objective = line.split()[1]
			elif line.startswith("Runtime:"):
				result.runtime = line.split()[1]
			elif line.startswith("Objective value:"):
				result.obj_value = line.split()[2]
			# mip specifics
			elif line.startswith("Gap:"):
				result.gap = float(line.split()[1])
				if result.gap > 0.25:
					print("High gap of {}".format(result.gap))
			elif line.startswith("Bounds:"):
				if not line.startswith("Bounds: None"):
					# slice string and split bounds into list
					bounds = line[9:-2].split(sep=", ")
					# convert bounds into float and store as tuple
					result.bounds = tuple(float(i) for i in bounds)
			elif line.startswith("model.status"):
				status = int(line.split()[1])
				print("{} has model.status {}".format(file, status))

				# infeasible
				if status == 3:
					# set obj_value to inf (similar to heuristic)
					result.obj_value = math.inf
					# set missing attributes to NA (not available)
					result.runtime = "NA"
					result.gap = "NA"
					result.cpu_over = "NA"
					result.mem_over = "NA"
					result.dr_over = "NA"
					result.changed = "NA"
					result.cpu = "NA"
					result.mem = "NA"
					result.dr = "NA"
					result.delay = "NA"

				# interrupted
				elif status == 11:
					# if the run was interrupted before a solution was found, it should be deleted (and rerun)
					print("{} was interrupted => may not include a feasible solution (if none was found before interrupt)".format(file))

			# heuristic specifics
			elif line.startswith("Seed:"):
				result.seed = line.split()[1]
			elif line.startswith("Pre-computation"):
				result.pre_runtime = line.split()[4]
			# metrics
			elif line.startswith("max_cpu_over-subscription:"):
				result.cpu_over = line.split()[1]
			elif line.startswith("max_mem_over-subscription:"):
				result.mem_over = line.split()[1]
			elif line.startswith("max_dr_over-subscription:"):
				result.dr_over = line.split()[1]
			elif line.startswith("changed"):
				result.changed = line.split()[1]
			elif line.startswith("total_cpu"):
				result.cpu = line.split()[1]
			elif line.startswith("total_mem"):
				result.mem = line.split()[1]
			elif line.startswith("total_dr"):
				result.dr = line.split()[1]
			elif line.startswith("total_delay"):
				result.delay = line.split()[1]
	return result


# check correctness of a result file: edge_delays matching edges, links_used matching links_dr
def check_correctness(file):
	print("\nChecking {}".format(file))
	with open(file, "r") as result_file:
		reading_edges, reading_delays = False, False
		reading_link_dr, reading_link_used = False, False
		edges, delays = [], []
		link_dr, link_used = [], []

		for line in result_file:
			# reset reading to False
			if line.startswith("# "):
				reading_edges = False
				reading_delays = False
				reading_link_dr = False
				reading_link_used = False

			# set current one to True
			if line.startswith("# edges: "):
				reading_edges = True
				continue		# skip header line
			elif line.startswith("# edge delays: "):
				reading_delays = True
				continue
			elif line.startswith("# link dr:"):
				reading_link_dr = True
				continue
			elif line.startswith("# link used:"):
				reading_link_used = True
				continue

			# actual reading
			if reading_edges:
				words = line.split()
				if len(words) >= 4:		# >= to include lines with comments
					edges.append((words[0], words[1], words[2]))
			elif reading_delays:
				words = line.split()
				if len(words) >= 4:
					delays.append((words[0], words[1], words[2]))
			elif reading_link_dr:
				words = line.split()
				if len(words) >= 6:
					link_dr.append((words[0], words[1], words[2], words[3], words[4]))
			elif reading_link_used:
				words = line.split()
				if len(words) >= 5:
					link_used.append((words[0], words[1], words[2], words[3], words[4]))

	# check if all edge delays are valid edges
	for i in delays:
		if i not in edges:
			print("edge delay {} not a valid edge".format(i))
	# check if all used links are actually used (have link_dr)
	for i in link_used:
		if i not in link_dr:
			print("link_used {} not really used (no link_dr)".format(i))


# compute actual max over-subscription based on the consumed resources and the network's capacities
def get_over_subscription(file):
	with open(file, "r") as result_file:
		# actual number of times a capacity was exceeded
		num_cpu_ex, num_mem_ex, num_dr_ex = -1, -1, -1
		# indicate whether cpu/mem/dr-header was parsed and the consumption is read
		reading_cpu, reading_mem, reading_dr = False, False, False
		# dicts initialized with resource consumption 0
		consumed_cpu, consumed_mem, consumed_dr = defaultdict(int), defaultdict(int), defaultdict(int)

		# read result_file line by line
		for line in result_file:
			# infeasible
			if line.startswith("model.status:"):
				if line.split()[1] == "3":
					return "NA", "NA", "NA"

			if reading_cpu:
				if len(line.split()) == 3:
					node = line.split()[1]
					cpu = float(line.split()[2])
					consumed_cpu[node] += cpu
				else:
					# stop reading after the last line
					reading_cpu = False
			# start reading after the header
			if line.startswith("# cpu req"):
				reading_cpu = True

			if reading_mem:
				if len(line.split()) == 3:
					node = line.split()[1]
					mem = float(line.split()[2])
					consumed_mem[node] += mem
				else:
					# stop reading after the last line
					reading_mem = False
			# start reading after the header
			if line.startswith("# mem req"):
				reading_mem = True

			if reading_dr:
				if len(line.split()) == 6:
					start = line.split()[3]
					end = line.split()[4]
					dr = float(line.split()[5])
					consumed_dr[(start, end)] += dr
				else:
					# stop reading after the last line
					reading_dr = False
			# start reading after the header
			if line.startswith("# link dr:"):
				reading_dr = True

	# compute the over-subscription based on the read consumption and the provided capacities
	over_cpu = {k:consumed_cpu[k]-nodes.cpu[k] for k in consumed_cpu.keys()}
	if len(over_cpu) > 0:
		over_cpu = max(max(over_cpu.values()), 0)
	else:
		over_cpu = 0
	over_mem = {k: consumed_mem[k] - nodes.mem[k] for k in consumed_mem.keys()}
	if len(over_mem) > 0:
		over_mem = max(max(over_mem.values()), 0)
	else:
		over_mem = 0
	over_dr = {k: consumed_dr[k] - links.dr[k] for k in consumed_dr.keys()}
	if len(over_dr) > 0:
		over_dr = max(max(over_dr.values()), 0)
	else:
		over_dr = 0

	return over_cpu, over_mem, over_dr


# read results from files
results = []
# check folder and subdirectories
if check_subdirs:
	for dirpath, dirnames, filenames in os.walk(folder):
		# exclude "old"-subdirectory
		if "old" in dirnames:
			dirnames.remove("old")

		result_files = [f for f in filenames if f.startswith(scenario) and f.endswith(".csv")]
		for file in result_files:
			result_file = os.path.join(dirpath, file)
			check_correctness(result_file)
			if only_check_correctness:
				continue
			result = read_file(result_file)
			# compute actual over-subscription of results of Pareto analysis (in which over-sub might not be minimized)
			if pareto or calc_over_sub:
				over_cpu, over_mem, over_dr = get_over_subscription(result_file)
				# override the recorded values (that are wrong if over-subscription isn't minimized)
				result.cpu_over = over_cpu
				result.mem_over = over_mem
				result.dr_over = over_dr
			results.append(result)

# only read files in specified folder; no subdirectories
else:
	for file in os.listdir(folder):
		if file.startswith(scenario) and file.endswith(".csv"):
			result_file = folder + "/" + file
			check_correctness(result_file)
			if only_check_correctness:
				continue
			result = read_file(result_file)
			# compute actual over-subscription of results of Pareto analysis (in which over-sub might not be minimized)
			if pareto or calc_over_sub:
				over_cpu, over_mem, over_dr = get_over_subscription(result_file)
				# override the recorded values (that are wrong if over-subscription isn't minimized)
				result.cpu_over = over_cpu
				result.mem_over = over_mem
				result.dr_over = over_dr
			results.append(result)

# write results to summary
# have to start with different prefix to avoid reading the result-summary and getting an error
if only_check_correctness:
	exit(0)
out_file = "{}/results_{}.csv".format(folder, scenario)
print("Writing result summary to {}".format(out_file))
with open(out_file, "w", newline="") as csvfile:
	writer = csv.writer(csvfile)
	# write header
	csvfile.write("sep=,\n")
	if mip:
		if pareto:
			# csvfile.write("name,src_no,src_dr,model,objective,bound1,bound2,bound3,runtime,obj_value,gap,cpu_over,mem_over,dr_over,changed,cpu,mem,dr,delay\n")
			csvfile.write("name,src_no,src_dr,model,objective,bound1,bound2,runtime,obj_value,gap,cpu_over,mem_over,dr_over,changed,cpu,mem,dr,delay\n")
		else:
			csvfile.write("name,src_no,src_dr,model,objective,runtime,obj_value,gap,cpu_over,mem_over,dr_over,changed,cpu,mem,dr,delay\n")
	else:
		csvfile.write("name,src_no,src_dr,model,seed,objective,pre_runtime,runtime,obj_value,cpu_over,mem_over,dr_over,changed,cpu,mem,dr,delay\n")
	# write result rows
	for r in results:
		if mip:
			if pareto:
				# writer.writerow((r.name, r.src_no, r.src_dr, r.model, r.objective, r.bounds[0], r.bounds[1], r.bounds[2], r.runtime, r.obj_value,
				# 				 r.gap, r.cpu_over, r.mem_over, r.dr_over, r.changed, r.cpu, r.mem, r.dr, r.delay))
				writer.writerow((r.name, r.src_no, r.src_dr, r.model, r.objective, r.bounds[0], r.bounds[1], r.runtime, r.obj_value,
								 r.gap, r.cpu_over, r.mem_over, r.dr_over, r.changed, r.cpu, r.mem, r.dr, r.delay))
			else:
				writer.writerow((r.name, r.src_no, r.src_dr, r.model, r.objective, r.runtime, r.obj_value, r.gap, r.cpu_over,
								 r.mem_over, r.dr_over, r.changed, r.cpu, r.mem, r.dr, r.delay))
		else:
			writer.writerow((r.name, r.src_no, r.src_dr, r.model, r.seed, r.objective, r.pre_runtime, r.runtime, r.obj_value,
							 r.cpu_over, r.mem_over, r.dr_over, r.changed, r.cpu, r.mem, r.dr, r.delay))
