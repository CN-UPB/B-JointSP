import math


# return the delay of the specified path (= list of nodes)
def path_delay(links, path):
    delay = 0
    # go along nodes of the path and increment delay for each traversed link
    for i in range(len(path) - 1):
        # skip connections on same node without a link (both inst at same node)
        if path[i] != path[i + 1]:
            delay += links.delay[(path[i], path[i+1])]
    return delay


# floyd-warshall algorithm
def all_pairs_shortest_paths(nodes, links):
    shortest_paths = {}		# key: (src, dest), value: (path, weight, delay)

    # initialize shortest paths
    for v1 in nodes.ids:
        for v2 in nodes.ids:
            # path from node to itself has weight 0
            if v1 == v2:
                shortest_paths[(v1, v2)] = ([v1, v2], 0)
            # path via direct link
            elif (v1, v2) in links.ids:
                shortest_paths[(v1, v2)] = ([v1, v2], links.weight((v1, v2)))
            # other paths are initialized with infinite weight
            else:
                shortest_paths[(v1, v2)] = ([v1, v2], math.inf)

    # indirect paths via intermediate node k
    for k in nodes.ids:
        for v1 in nodes.ids:
            for v2 in nodes.ids:
                # use k if it reduces the path weight
                if shortest_paths[(v1, v2)][1] > shortest_paths[(v1, k)][1] + shortest_paths[(k, v2)][1]:
                    # new path via intermediate node k (when adding the two paths, k is excluded from the second path)
                    new_path = shortest_paths[(v1, k)][0] + shortest_paths[(k, v2)][0][1:]
                    new_weight = shortest_paths[(v1, k)][1] + shortest_paths[(k, v2)][1]
                    shortest_paths[(v1, v2)] = (new_path, new_weight)

    # update dictionary to include delay for each path
    shortest_paths = {k:(v[0], v[1], path_delay(links, v[0])) for k,v in shortest_paths.items()}

    return shortest_paths
