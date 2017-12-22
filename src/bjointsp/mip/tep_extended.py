from gurobipy import *
from datetime import datetime
from collections import defaultdict
import bjointsp.objective as objective


# return name of log-file: logs/scenario_timestamp_bounds.log => unique name if not >1 run per second and scenario
def log_name(scenario, obj, bounds="", rep=None):
	input_file = os.path.basename(scenario)
	input_directory = os.path.dirname(scenario)
	log_directory = os.path.join(input_directory, "../logs/mip/obj{}".format(obj))
	if rep is not None:
		log_directory += "/{}".format(rep)
	split_file = input_file.split(".")
	timestamp = datetime.now().strftime("_%Y-%m-%d_%H-%M-%S")
	log_file = split_file[0] + timestamp + bounds + ".log"
	log_path = os.path.join(log_directory, log_file)
	os.makedirs(os.path.dirname(log_path), exist_ok=True)  # create subdirectories if necessary

	return log_path


# return whether j1 is linked to j2 via an arbitrary number of forward arcs
def arcs_between(components, arcs, j1, j2):
	if not j1 in components or not j2 in components:
		return False    # j1 or j2 are not components of the template

	from_j1 = [a for a in arcs if a.source == j1 and a.direction == "forward"]
	and_to_j2 = [a for a in from_j1 if a.dest == j2]
	if len(from_j1) == 0:       # no outgoing arcs from j1 => not linked
		return False
	elif len(and_to_j2) > 0:    # directly linked to j2 via an arc => linked
		return True
	else:                       # not directly linked => check next component(s) in chain/graph
		for a in from_j1:
			return arcs_between(components, arcs, a.dest, j2)


def solve(nodes, links, templates, prev_embedding, sources, fixed, scenario, obj, bounds=None, rep=None):
	links = tuplelist(links)		# convert into Gurobi tuplelist to use efficient select with wildcards
	model = Model("tep_extended")

	if bounds is not None:
		model.params.LogFile = log_name(scenario, obj, bounds="_({},{},{})".format(bounds[0], bounds[1], bounds[2]))
		# model.params.LogFile = log_name(scenario, obj, bounds="_({},{})".format(bounds[0], bounds[1]), rep=rep)
	else:
		model.params.LogFile = log_name(scenario, obj, rep=rep)

	model.params.Threads = 1
	# MIPFocus=1 => focus on feasibility; 2 => focus on optimality; 3 => focus on best bound; 0 => balance (default)
	# model.params.MIPFocus = 2

	# create set of components and arcs
	components = set()
	arcs = set()
	for template in templates:
		components.update(template.components)
		arcs.update(template.arcs)

	# print input
	print("Objective: {}, Bounds: {}".format(obj, bounds))
	print("Templates:", *templates, sep=" ")
	print("Components:", *components, sep=" ")
	print("Arcs:", *arcs, sep=" ")
	print("Sources:", *sources, sep=" ")
	print("Fixed instances:", *fixed, sep=" ")
	if prev_embedding:
		print("Previous overlay exists")
	else:
		print("No previous overlay exists")

	# set of all flows
	flows = set()
	for s in sources:
		flows = flows.union(s.flows)
	print("Flows:", end=" "),
	for f in flows:
		print(f.full_str(), end=" "),
	print()

	# set old instance locations based on previous overlay
	old = {}
	for j in components:
		for v in nodes.ids:
			if v in prev_embedding[j]:
				old[j, v] = 1
			else:
				old[j, v] = 0


	# VARIABLES
	# instances, ingoing/outgoing data rate, cpu/mem requirements, changed instances
	instance, ingoing, outgoing, cpu_req, mem_req, changed = {}, {}, {}, {}, {}, {}
	ingoing_back, outgoing_back = {}, {}
	for j in components:
		for v in nodes.ids:
			instance[j, v] = model.addVar(vtype=GRB.BINARY, name="instance_%s_%s" % (j, v))
			changed[j, v] = model.addVar(vtype=GRB.BINARY, name="changed_%s_%s" % (j, v))
			cpu_req[j, v] = model.addVar(lb=0, name="cpu_req_%s_%s" % (j, v))
			mem_req[j, v] = model.addVar(lb=0, name="mem_req_%s_%s" % (j, v))

			for f in flows:
				for k in range(j.inputs):
					ingoing[j, v, f, k] = model.addVar(lb=0, name="ingoing_fwd_%s_%s_%s_%d" % (j, v, f, k))
				for k in range(j.outputs):
					outgoing[j, v, f, k] = model.addVar(lb=0, name="outgoing_fwd_%s_%s_%s_%d" % (j, v, f, k))
				for k in range(j.inputs_back):
					ingoing_back[j, v, f, k] = model.addVar(lb=0, name="ingoing_bwd_%s_%s_%s_%d" % (j, v, f, k))
				for k in range(j.outputs_back):
					outgoing_back[j, v, f, k] = model.addVar(lb=0, name="outgoing_bwd_%s_%s_%s_%d" % (j, v, f, k))

	# edge y (edge exists or not), link_drs z, links used
	edge, link_dr, link_used = {}, {}, {}
	for a in arcs:
		for v1 in nodes.ids:
			for v2 in nodes.ids:
				for f in flows:
					edge[a, v1, v2, f] = model.addVar(vtype=GRB.BINARY, name="edge_%s_%s_%s_%s" % (a, v1, v2, f))

				for l in links.ids:
					link_dr[a, v1, v2, l] = model.addVar(lb=0, name="link_dr_%s_%s_%s_%s" % (a, v1, v2, l))
					link_used[a, v1, v2, l] = model.addVar(vtype=GRB.BINARY, name="link_used_%s_%s_%s_%s" % (a, v1, v2, l))

	# capacity exceeded
	max_cpu = model.addVar(lb=0, name="max_cpu_over-subscription")
	max_mem = model.addVar(lb=0, name="max_mem_over-subscription")
	max_dr = model.addVar(lb=0, name="max_dr_over-subscription")

	# passes: whether flow f passes an instance of j at v (in fwd/bwd direction)
	passes_fwd, passes_bwd = {}, {}
	for j in components:
		for v in nodes.ids:
			for f in flows:
				passes_fwd[j, v, f] = model.addVar(vtype=GRB.BINARY, name="passes_fwd_%s_%s_%s" % (j, v, f))
				passes_bwd[j, v, f] = model.addVar(vtype=GRB.BINARY, name="passes_bwd_%s_%s_%s" % (j, v, f))

	# edge delay (just for evaluation)
	edge_delay = {}
	for a in arcs:
		for v1 in nodes.ids:
			for v2 in nodes.ids:
				edge_delay[a, v1, v2] = model.addVar(lb=0, name="edge_delay_%s_%s_%s" % (a, v1, v2))

	model.update()


	# CONSTRAINTS
	# BIG_M must be large enough to avoid infeasibilty/unsolvability
	# but small enough to 1/BIG_M being (10x) larger than model.params.IntFeasTol (def: 1e-05) to avoid wrong integers
	BIG_M = 1000
	int_tolerance = model.params.IntFeasTol
	print("Big M: %d, IntFeasTol: %s" % (BIG_M, int_tolerance))
	if int_tolerance*10 >= 1 / BIG_M:
		raise ValueError("Big M (%s) is too big compared to IntFeasTol (%s) -> adjust Big M or IntFeasTol" % (BIG_M, int_tolerance))

	# create dictionaries of source components (key) and list of locations, data rates (value) for sources
	src_loc = defaultdict(list)
	for src in sources:
		src_loc[src.component].append(src.location)

	# dictionary with source flows: for each source (j,v) a list of flows originating from there
	src_flows = defaultdict(list)
	for src in sources:
		src_flows[(src.component, src.location)].extend(src.flows)

	# mapping consistency rules
	for src_comp in src_loc:
		for v in src_loc[src_comp]:
			# place source instances at the specified locations
			model.addConstr(instance[src_comp, v] == 1, name="source_mapped")

			# each output of src has the specified data rate of the flows; currently only support 1 output at source
			for f in flows:
				for k in range(src_comp.outputs):
					# only set the flows to leave the specified sources (and have 0 dr leaving other sources)
					if f in src_flows[(src_comp, v)]:
						model.addConstr(outgoing[src_comp, v, f, k] == f.src_dr, name="source_flows1")
					# set dr to 0 for other sources
					else:
						model.addConstr(outgoing[src_comp, v, f, k] == 0, name="source_flows2")

		# no instances of source components at any nodes without sources (for way back)
		for v in nodes.ids:
			if v not in src_loc[src_comp]:	# not a location of a source
				model.addConstr(instance[src_comp, v] == 0, name="source_not_mapped")

	for j in components:
		for v in nodes.ids:
			if old[j, v] == 0:
				# changed iff instance added (inst=1)
				model.addConstr(changed[j, v] == instance[j, v], name="added")
			elif old[j, v] == 1:
				# changed iff instance removed (inst=0)
				model.addConstr(changed[j, v] == 1 - instance[j, v], name="removed")
			else:
				raise ValueError("Invalid value for old instance ({},{}): {}".format(j, v, old[j, v]))

			for f in flows:
				for k in range(j.inputs):
					model.addConstr(ingoing[j, v, f, k] <= BIG_M * instance[j, v], name="instance_mapped1")
				for k in range(j.outputs):
					model.addConstr(outgoing[j, v, f, k] <= BIG_M * instance[j, v], name="instance_mapped2")
				for k in range(j.inputs_back):
					model.addConstr(ingoing_back[j, v, f, k] <= BIG_M * instance[j, v], name="instance_mapped3")
				for k in range(j.outputs_back):
					model.addConstr(outgoing_back[j, v, f, k] <= BIG_M * instance[j, v], name="instance_mapped4")


	# flow and data rate rules
	for j in components:
		if not j.source:
			for v in nodes.ids:
				for f in flows:
					if not j.end:	# normal component
						in_vector = []    # create ingoing data rate vector
						zero_vector = []
						# zero vector
						for k in range(j.inputs):
							in_vector.append(ingoing[j, v, f, k])
							zero_vector.append(0)
						for k in range(j.outputs):
							model.addConstr(outgoing[j, v, f, k] == j.outgoing(in_vector, k)
											- (1 - instance[j, v]) * j.outgoing(zero_vector, k), name="out_dr_fwd")

						in_vector = []     # same for way back
						zero_vector = []
						for k in range(j.inputs_back):
							in_vector.append(ingoing_back[j, v, f, k])
							zero_vector.append(0)
						for k in range(j.outputs_back):
							model.addConstr(outgoing_back[j, v, f, k] == j.outgoing_back(in_vector, k)
											- (1 - instance[j, v]) * j.outgoing_back(zero_vector, k), name="out_dr_bwd")

					else:   # end component
						in_vector = []      # create ingoing data rate vector
						zero_vector = []
						for k in range(j.inputs):
							in_vector.append(ingoing[j, v, f, k])
							zero_vector.append(0)
						for k in range(j.outputs_back):
							model.addConstr(outgoing_back[j, v, f, k] == j.outgoing_back(in_vector, k)
											- (1 - instance[j, v]) * j.outgoing_back(zero_vector, k), name="out_dr_end")


	# UNSPLITTABLE FLOWS
	# set "passes" iff an ingoing or outgoing dr are > 0 (in fwd/bwd direction)
	for j in components:
		for v in nodes.ids:
			for f in flows:
				model.addConstr(BIG_M * passes_fwd[j, v, f] >= quicksum(ingoing[j, v, f, k] for k in range(j.inputs))
								+ quicksum(outgoing[j, v, f, k] for k in range(j.outputs)), name="flow_passes_fwd")
				model.addConstr(passes_fwd[j, v, f] <= BIG_M * (quicksum(ingoing[j, v, f, k] for k in range(j.inputs))
								+ quicksum(outgoing[j, v, f, k] for k in range(j.outputs))), name="flow_passes_fwd_not")
				model.addConstr(BIG_M * passes_bwd[j, v, f] >= quicksum(ingoing_back[j, v, f, k] for k in range(j.inputs_back))
								+ quicksum(outgoing_back[j, v, f, k] for k in range(j.outputs_back)), name="flow_passes_bwd")
				model.addConstr(passes_bwd[j, v, f] <= BIG_M * (quicksum(ingoing_back[j, v, f, k] for k in range(j.inputs_back))
								+ quicksum(outgoing_back[j, v, f, k] for k in range(j.outputs_back))), name="flow_passes_bwd_not")

	# assign each flow to exactly one edge v1->v2 iff the flow passes v1 at all (else 0) -> non-splittable
	# distinguish forward and backward direction: one instance may be traversed in fwd and another in bwd (if not stateful)
	for a in arcs:
		for v1 in nodes.ids:
			for f in flows:
				if a.source.end:
					# end components are passed in fwd direction (fwd inputs) but create 1 edge in bwd direction
					model.addConstr(quicksum(edge[a, v1, v2, f] for v2 in nodes.ids) == passes_fwd[a.source, v1, f], name="1_edge_end")
				else:
					# create 1 fwd edge iff passed in fwd direction (same for bwd)
					if a.direction == "forward":
						model.addConstr(quicksum(edge[a, v1, v2, f] for v2 in nodes.ids) == passes_fwd[a.source, v1, f], name="1_edge_fwd")
					else:
						model.addConstr(quicksum(edge[a, v1, v2, f] for v2 in nodes.ids) == passes_bwd[a.source, v1, f], name="1_edge_bwd")

	# if a flow is going along an edge, its entire data rate is assigned to the connected instance
	# look at the sum from all different v1: each flow only uses at most one edge from one v1
	for a in arcs:
		for v2 in nodes.ids:
			for f in flows:
				if a.direction == "forward":
					model.addConstr(quicksum(outgoing[a.source, v1, f, a.src_out] * edge[a, v1, v2, f] for v1 in nodes.ids)
									== ingoing[a.dest, v2, f, a.dest_in], name="edge_fwd")
				else:
					model.addConstr(quicksum(outgoing_back[a.source, v1, f, a.src_out] * edge[a, v1, v2, f] for v1 in nodes.ids)
									== ingoing_back[a.dest, v2, f, a.dest_in], name="edge_bwd")

	# flow conservation
	for a in arcs:
		for v in nodes.ids:
			for v1 in nodes.ids:
				for v2 in nodes.ids:
					if v != v1 and v != v2:
						model.addConstr(quicksum(link_dr[a, v1, v2, l] for l in links.ids.select(v, '*')) -
										quicksum(link_dr[a, v1, v2, l] for l in links.ids.select('*', v)) == 0,
										name="flow_conservation_through")
					if v == v1 and v1 != v2:
						# take the data rate of all flows along arc a over the link (ie, sum over f)
						if a.direction == "forward":
							model.addConstr(quicksum(link_dr[a, v1, v2, l] for l in links.ids.select(v, '*')) -
											quicksum(link_dr[a, v1, v2, l] for l in links.ids.select('*', v))
											== quicksum(edge[a, v1, v2, f] * outgoing[a.source, v1, f, a.src_out] for f in flows),
											name="flow_conservation_out_fwd")
						else:
							model.addConstr(quicksum(link_dr[a, v1, v2, l] for l in links.ids.select(v, '*')) -
											quicksum(link_dr[a, v1, v2, l] for l in links.ids.select('*', v))
											== quicksum(edge[a, v1, v2, f] * outgoing_back[a.source, v1, f, a.src_out] for f in flows),
											name="flow_conservation_out_bwd")
					if v == v1 and v == v2:
						model.addConstr(quicksum(link_dr[a, v1, v2, l] for l in links.ids.select(v, '*')) -
										quicksum(link_dr[a, v1, v2, l] for l in links.ids.select('*', v)) == 0,
										name="flow_conservation_same")

	for a in arcs:
		for v1 in nodes.ids:
			for v2 in nodes.ids:
				for l in links.ids:
					model.addConstr(link_dr[a, v1, v2, l] <= BIG_M * link_used[a, v1, v2, l], name="link_used")
					model.addConstr(link_used[a, v1, v2, l] <= BIG_M * link_dr[a, v1, v2, l], name="link_not_used")

					# ensure that no edge uses the same link in fwd and bwd direction, ie, v1->v2 and v1<-v2
					# otherwise the link_drs substract each other in the flow cons. and can be arbitrarily high if link_dr is not minimized (in Pareto analysis)
					# only consider links that exist in reverse direction
					l_rev = (l[1], l[0])
					if l_rev in links.ids:
						model.addConstr(link_used[a, v1, v2, l] + link_used[a, v1, v2, l_rev] <= 1, name="no_rev_link")

					# links can only be used by existing edges
					model.addConstr(link_used[a, v1, v2, l] <= quicksum(edge[a, v1, v2, f] for f in flows), name="no_wrong_links")


	# resource consumption
	for j in components:
		for v in nodes.ids:
			in_vector = []  # create ingoing data rate vector (first with forward inputs then backward)
			zero_vector = []
			# sum up the dr over all flows at each input to determine the resource consumption
			for k in range(j.inputs):
				in_vector.append(quicksum(ingoing[j, v, f, k] for f in flows))
				zero_vector.append(0)
			for k in range(j.inputs_back):
				in_vector.append(quicksum(ingoing_back[j, v, f, k] for f in flows))
				zero_vector.append(0)

			# resource requirements of both directions sum up
			model.addConstr(cpu_req[j, v] == j.cpu_req(in_vector)
							- (1 - instance[j, v]) * j.cpu_req(zero_vector), name="cpu_consumption")
			model.addConstr(mem_req[j, v] == j.mem_req(in_vector)
							- (1 - instance[j, v]) * j.mem_req(zero_vector), name="mem_consumption")


	# capacity constraints
	for v in nodes.ids:
		model.addConstr(quicksum(cpu_req[j, v] for j in components)
						- nodes.cpu[v] <= max_cpu, name="cpu_capacity")
		model.addConstr(quicksum(mem_req[j, v] for j in components)
						- nodes.mem[v] <= max_mem, name="mem_capacity")

	for l in links.ids:
		model.addConstr(quicksum(link_dr[a, v1, v2, l] for a in arcs for v1 in nodes.ids for v2 in nodes.ids)
						- links.dr[l] <= max_dr, name="link_capacity")


	# STATEFUL CONSTRAINT
	# iff a flow traverses a stateful instance in fwd direction, it has to traverse it in bwd direction
	for j in components:
		if j.stateful:
			for v in nodes.ids:
				for f in flows:
					model.addConstr(passes_fwd[j, v, f] == passes_bwd[j, v, f], name="stateful")


	# FIXED INSTANCES
	# create dictionary of components (key) and list of locations (value) for fixed instances
	fixed_dict = defaultdict(list)
	for f in fixed:
		fixed_dict[f.component].append(f.location)

	# fixed instances have to be (only) placed at their fixed locations; similar to sources
	for j in fixed_dict:
		for v in nodes.ids:
			if v in fixed_dict[j]:
				model.addConstr(instance[j, v] == 1, name="fixed1")  	# at fixed location
			else:
				model.addConstr(instance[j, v] == 0, name="fixed2")		# nowhere else


	# BOUND MAX DELAY
	# for each arc a, all edges v1->v2 must have a delay <= a.max_delay
	for a in arcs:
		for v1 in nodes.ids:
			for v2 in nodes.ids:
				model.addConstr(quicksum(link_used[a, v1, v2, l] * links.delay[l] for l in links.ids) <= a.max_delay,
								name="max_delay")

				# also record actual delay
				model.addConstr(quicksum(link_used[a, v1, v2, l] * links.delay[l] for l in links.ids) == edge_delay[a, v1, v2],
					name="edge_delay")


	# OBJECTIVE
	# lexicographical combination of all objectives
	if obj == objective.COMBINED:
		w1 = 100*1000*1000		# assuming changed instances < 100
		w2 = 1000*1000			# assuming total resource consumption < 1000
		w3 = 1000				# assuming total delay < 1000
		model.setObjective(w1 * (max_cpu + max_mem + max_dr)
						   + w2 * quicksum(changed[j, v] for j in components for v in nodes.ids)
						   + w3 * (quicksum(cpu_req[j, v] + mem_req[j, v] for j in components for v in nodes.ids)
								   + quicksum(link_dr[a, v1, v2, l] for a in arcs for v1 in nodes.ids for v2 in nodes.ids for l in links.ids))
						   + quicksum(links.delay[l] * link_used[a, v1, v2, l] for a in arcs for v1 in nodes.ids
									  for v2 in nodes.ids for l in links.ids))

	# also bound other objectives if bounds are provided (for Pareto analysis)
	# NOTE: Currently only support minimizing and bounding obj1-3, not obj4 (delay); corresponding lines are commented out
	# obj1: minimize max over-subscription
	elif obj == objective.OVER_SUB:
		# bound other objectives/metrics
		if bounds is not None:
			model.addConstr(quicksum(changed[j, v] for j in components for v in nodes.ids) <= bounds[0], name="bound_changed")
			model.addConstr(quicksum(cpu_req[j, v] + mem_req[j, v] for j in components for v in nodes.ids)
						   + quicksum(link_dr[a, v1, v2, l] for a in arcs for v1 in nodes.ids for v2 in nodes.ids for l in links.ids)
							<= bounds[1], name="bound_resources")
			model.addConstr(quicksum(links.delay[l] * link_used[a, v1, v2, l] for a in arcs for v1 in nodes.ids
									for v2 in nodes.ids for l in links.ids) <= bounds[2], name="bound_delay")
		model.setObjective(max_cpu + max_mem + max_dr)

	# obj2: minimize changed instances (compared to previous embedding)
	elif obj == objective.CHANGED:
		if bounds is not None:
			model.addConstr(max_cpu + max_mem + max_dr <= bounds[0], name="bound_over-sub")
			model.addConstr(quicksum(cpu_req[j, v] + mem_req[j, v] for j in components for v in nodes.ids)
						   + quicksum(link_dr[a, v1, v2, l] for a in arcs for v1 in nodes.ids for v2 in nodes.ids for l in links.ids)
							<= bounds[1], name="bound_resources")
			model.addConstr(quicksum(links.delay[l] * link_used[a, v1, v2, l] for a in arcs for v1 in nodes.ids
									for v2 in nodes.ids for l in links.ids) <= bounds[2], name="bound_delay")
		model.setObjective(quicksum(changed[j, v] for j in components for v in nodes.ids))

	# obj3: minimize total resource consumption
	elif obj == objective.RESOURCES:
		if bounds is not None:
			model.addConstr(max_cpu + max_mem + max_dr <= bounds[0], name="bound_over-sub")
			model.addConstr(quicksum(changed[j, v] for j in components for v in nodes.ids) <= bounds[1],
							name="bound_changed")
			model.addConstr(quicksum(links.delay[l] * link_used[a, v1, v2, l] for a in arcs for v1 in nodes.ids
									 for v2 in nodes.ids for l in links.ids) <= bounds[2], name="bound_delay")
		model.setObjective(quicksum(cpu_req[j, v] + mem_req[j, v] for j in components for v in nodes.ids)
						   + quicksum(link_dr[a, v1, v2, l] for a in arcs for v1 in nodes.ids for v2 in nodes.ids for l in links.ids))

	# obj4: minimize total delay
	elif obj == objective.DELAY:
		if bounds is not None:
			model.addConstr(max_cpu + max_mem + max_dr <= bounds[0], name="bound_over-sub")
			model.addConstr(quicksum(changed[j, v] for j in components for v in nodes.ids) <= bounds[1],
							name="bound_changed")
			model.addConstr(quicksum(cpu_req[j, v] + mem_req[j, v] for j in components for v in nodes.ids)
							+ quicksum(link_dr[a, v1, v2, l] for a in arcs for v1 in nodes.ids for v2 in nodes.ids for l in links.ids)
							<= bounds[2], name="bound_resources")
		model.setObjective(quicksum(links.delay[l] * link_used[a, v1, v2, l] for a in arcs for v1 in nodes.ids
									for v2 in nodes.ids for l in links.ids))

	else:
		raise ValueError("Objective {} unknown".format(obj))


	model.optimize()


	# SOLUTION
	PRINT_DETAILS = False
	if model.status == GRB.Status.OPTIMAL:
		print('The optimal objective is %g' % model.objVal)

		if PRINT_DETAILS:   # all variables != 0
			for v in model.getVars():  # print all variables != 0
				if round(v.x, 3) > 0:		# avoid values = 0/-0 or very close to 0
					print('%s %g' % (v.varName, v.x))

		else:   # only some information in nicer formatting
			if round(max_cpu.X, 3) > 0:
				print("!Max CPU over-subscription: {}".format(max_cpu.X))
			if round(max_mem.X, 3) > 0:
				print("!Max memory over-subscription: {}".format(max_mem.X))
			if round(max_dr.X, 3) > 0:
				print("!Max data rate over-subscription: {}".format(max_dr.X))

			instance = model.getAttr("x", instance)
			for v in nodes.ids:
				for j in components:
					if round(instance[j, v]) > 0:
						print("Instance of %s at %s" % (j, v))

			print()
			edge = model.getAttr("x", edge)
			for a1 in arcs:
				for v1 in nodes.ids:
					for v2 in nodes.ids:
						for f in flows:
							if round(edge[a1, v1, v2, f]) > 0:
								print("edge %s from %s to %s (flow %s)" % (a1, v1, v2, f.id))

			print()
			in_dr_fwd = model.getAttr("x", ingoing)
			in_dr_bwd = model.getAttr("x", ingoing_back)
			out_dr_fwd = model.getAttr("x", outgoing)
			out_dr_bwd = model.getAttr("x", outgoing_back)
			# forward
			for j in components:
				for v in nodes.ids:
					for f in flows:
						for k in range(j.inputs):
							if round(in_dr_fwd[j, v, f, k], 3) > 0:
								print("ingoing_fwd of ({}, {}).{} (flow {}): {}".format(j, v, k, f.id, in_dr_fwd[j, v, f, k]))
						for k in range(j.outputs):
							if round(out_dr_fwd[j, v, f, k], 3) > 0:
								print("outgoing_fwd of ({}, {}).{} (flow {}): {}".format(j, v, k, f.id, out_dr_fwd[j, v, f, k]))
			print()
			# backward
			for j in components:
				for v in nodes.ids:
					for f in flows:
						for k in range(j.inputs_back):
							if round(in_dr_bwd[j, v, f, k], 3) > 0:
								print("ingoing_bwd of ({}, {}).{} (flow {}): {}".format(j, v, k, f.id, in_dr_bwd[j, v, f, k]))
						for k in range(j.outputs_back):
							if round(out_dr_bwd[j, v, f, k], 3) > 0:
								print("outgoing_bwd of ({}, {}).{} (flow {}): {}".format(j, v, k, f.id, out_dr_bwd[j, v, f, k]))


	# computing the IIS raises an exception when bounds are too tight => commented out for Pareto analysis
	# elif model.status == GRB.Status.INFEASIBLE:   # do IIS (if infeasible)
	# 	print("The model is infeasible; computing IIS")
	# 	model.computeIIS()
	# 	print("\nThe following constraint(s) cannot be satisfied:")
	# 	for c in model.getConstrs():
	# 		if c.IISConstr:
	# 			print("%s" % c.constrName)

	return model
