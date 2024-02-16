import pyomo.pysp.util.rapper as rapper
from pyomo.pysp.scenariotree.tree_structure_model import CreateAbstractScenarioTreeModel

solvername = 'cplex'
path = str(pathlib.Path(__file__).parent.absolute())

abstract_tree = CreateAbstractScenarioTreeModel()
concrete_tree = abstract_tree.create_instance(path + '/ScenarioStructure.dat')

stsolver = rapper.StochSolver(fsfile=path + '/ReferenceModel.py',
                                # fsfct='pysp_instance_creation_callback',
                                tree_model=concrete_tree)

# ef_sol = stsolver.solve_ef(solvername)

ef_sol = stsolver.solve_ef(solvername,
                            generate_weighted_cvar=True,
                            cvar_weight=1.0,
                            risk_alpha=0.1)
