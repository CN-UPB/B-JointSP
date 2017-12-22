# separate writer for MIP results, depending on gurobipy (for model status) --> regular writer doesn't need gurobipy
from gurobipy import GRB


def model_status(model):
	if model.status == GRB.status.OPTIMAL:
		return "optimal"
	elif model.status == GRB.status.INTERRUPTED or model.status == GRB.status.SUBOPTIMAL:
		return "suboptimal"
	elif model.status == GRB.status.INFEASIBLE:
		return "infeasible"
	else:
		raise ValueError("Unknown model status: {}".format(model.status))
