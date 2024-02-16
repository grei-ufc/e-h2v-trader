# Descrição do problema estocástico *The Farmer Problem*

Birge and Louveaux [BirgeLouveauxBook] make use of the example of a farmer with the following data:

- *500 acres* that can be planted in *wheat, corn or sugar beets*, at a *per acre cost of 150, 230 and 260* (Euros, presumably), respectively.

- The farmer needs to have *at least 200 tons of wheat and 240 tons of corn to use as feed*, but if enough is not grown, *those crops can be purchased for 238 and 210*, respectively.

- *Corn and wheat grown in excess of the feed requirements can be sold for 170 and 150*, respectively. 

- *A price of 36 per ton is guaranteed for the first 6000 tons grown by any farmer*, but *beets in excess of that are sold for 10 per ton*. 

- The *yield is 2.5, 3, and 20 tons per acre for wheat, corn and sugar beets*, respectively.

So far, **this is a deterministic problem because we are assuming that we know all the data**.

The data described above are in the file *ReferenceModel.dat* in root directory, wich is the same data in file *AverageScenario.dat* in the sub-directory ./scenariodata

Any of the data in *ReferenceModel.dat* could be modeled as uncertain, but *we will consider only the possibility that the yield per acre could be higher or lower than expected*.

Assume that:

There is *a probability of 1/3 that the yields will be the average values that were given* (i.e., wheat 2.5; corn 3; and beets 20).

And:

There is *a 1/3 probability that they will be lower* (2, 2.4, 16) 

And

*1/3 probability they will be higher* (3, 3.6, 24).

We refer to *each full set of data as a scenario* and collectively we call them a scenario tree.

> In this case the scenario tree is very simple: *there is a root node and three leaf nodes*: one corresponding to each scenario. 

1. The acreage-to-plant decisions are root node decisions because they must be made without knowing what the yield will be.
2. The other variables are so-called second stage decisions, because they will depend on which scenario is realized.

PySP requires that *users describe the scenario tree* using specific constructs in *a file named ScenarioStructure.dat*; 

For the farmer problem, this file can be found in the *./scenariodata/ScenarioStructure.dat*.

For more informations on the ScenarioStructure.dat syntax, please refer to this [link](https://pysp.readthedocs.io/en/latest/pysp.html#scenariostructure-dat)

So far, we have given:
- *a model* in the file named *ReferenceModel.py*, 
- a set of deterministic data in the file named *ReferenceModel.dat*, and
- a description of the stochastics in the file named *ScenarioStructure.dat*.

All that remains is to give the data for each scenario. There are two ways to do that in PySP:
- *scenario-based* and
- *node-based*.

The default is scenario-based so we will describe that first.

For scenario-based data, the full data for each scenario is given in a .dat file with the root name that is the name of the scenario.

So, for example, the file named AverageScenario.dat must contain all the data for the model for the scenario named “AvererageScenario.”

It turns out that this file can be created by simply copying the file ReferenceModel.dat as shown above because it contains a full set of data for the “AverageScenario” scenario.

The files *BelowAverageScenario.dat* and *AboveAverageScenario.dat* will differ from this file and from each other only in their last line, *where the yield is specified*. 

These three files are in the sub-directory ./scenariodata along with ScenarioStructure.dat and ReferenceModel.dat.

**Scenario-based data wastes resources by specifying the same thing over and over again!**. 

In many cases, that does not matter and it is convenient to have full scenario data files available (for one thing, the scenarios can easily be run independently using the pyomo command). 

However, in many other settings, *it is better to use a node-based specification where the data that is unique to each node is specified in a .dat file with a root name that matches the node name*.

In the farmer example, the file RootNode.dat will be the same as ReferenceModel.dat except that it will lack the last line that specifies the yield. 

The files *BelowAverageNode.dat*, *AverageNode.dat*, and *AboveAverageNode.dat* will contain only one line each to specify the yield.

> [!Tip]
> If node-based data is to be used, then the ScenarioStructure.dat file must contain the following line:
> param ScenarioBasedData := False ;

An entire set of files for node-based data for the farmer problem are in the sub-directory ./nodedata


# Running the scripts

## Deterministic
pyomo solve --solver=cplex farmer-prob/ReferenceModel.py farmer-prob/scenariodata/AverageScenario.dat
*Or*
pyomo solve --solver=cplex farmer-prob/ReferenceModel.py farmer-prob/ReferenceModel.dat

Output:

```sh
[    0.00] Setting up Pyomo environment
[    0.00] Applying Pyomo preprocessing actions
[    0.00] Creating model
[    0.01] Applying solver
[    0.02] Processing results
    Number of solutions: 1
    Solution Information
      Gap: 0.0
      Status: optimal
      Function Value: -118600.0
    Solver results file: results.yml
[    0.02] Applying Pyomo postprocessing actions
[    0.02] Pyomo Finished

```


## Probabilistic based in scenarios
runef -m farmer-prob -s farmer-prob/scenariodata --solver=cplex --solve

Output:
```sh
Initializing extensive form algorithm for stochastic programming problems.
EF solve completed and solution status is optimal
EF solve termination condition is optimal
EF objective: -108390.00001
EF gap:            0.00000
EF bound:     -108390.00001

Extensive form solution:
----------------------------------------------------
Tree Nodes:

	Name=AboveAverageNode
	Stage=SecondStage
	Parent=RootNode
	Variables: 
		QuantitySubQuotaSold[CORN]=48.0
		QuantitySubQuotaSold[SUGAR_BEETS]=6000.0
		QuantitySubQuotaSold[WHEAT]=310.0

	Name=AverageNode
	Stage=SecondStage
	Parent=RootNode
	Variables: 
		QuantitySubQuotaSold[SUGAR_BEETS]=5000.0
		QuantitySubQuotaSold[WHEAT]=225.0

	Name=BelowAverageNode
	Stage=SecondStage
	Parent=RootNode
	Variables: 
		QuantityPurchased[CORN]=48.0
		QuantitySubQuotaSold[SUGAR_BEETS]=4000.0
		QuantitySubQuotaSold[WHEAT]=140.0

	Name=RootNode
	Stage=FirstStage
	Parent=None
	Variables: 
		DevotedAcreage[CORN]=80.0
		DevotedAcreage[SUGAR_BEETS]=250.0
		DevotedAcreage[WHEAT]=170.0


Extensive form costs:
Scenario Tree Costs
----------------------------------------------------
Tree Nodes:

	Name=AboveAverageNode
	Stage=SecondStage
	Parent=RootNode
	Conditional probability=0.3333
	Children:
		None
	Scenarios:
		AboveAverageScenario
	Expected cost of (sub)tree rooted at node=-275900.0000

	Name=AverageNode
	Stage=SecondStage
	Parent=RootNode
	Conditional probability=0.3333
	Children:
		None
	Scenarios:
		AverageScenario
	Expected cost of (sub)tree rooted at node=-218250.0000

	Name=BelowAverageNode
	Stage=SecondStage
	Parent=RootNode
	Conditional probability=0.3333
	Children:
		None
	Scenarios:
		BelowAverageScenario
	Expected cost of (sub)tree rooted at node=-157720.0000

	Name=RootNode
	Stage=FirstStage
	Parent=None
	Conditional probability=1.0000
	Children:
		AboveAverageNode
		AverageNode
		BelowAverageNode
	Scenarios:
		AboveAverageScenario
		AverageScenario
		BelowAverageScenario
	Expected cost of (sub)tree rooted at node=-108390.0000

----------------------------------------------------
Scenarios:

	Name=AboveAverageScenario
	Probability=0.3333
	Leaf Node=AboveAverageNode
	Tree node sequence:
		RootNode
		AboveAverageNode
	Stage=          FirstStage     Cost=108900.0000
	Stage=         SecondStage     Cost=-275900.0000
	Total scenario cost=-167000.0000

	Name=AverageScenario
	Probability=0.3333
	Leaf Node=AverageNode
	Tree node sequence:
		RootNode
		AverageNode
	Stage=          FirstStage     Cost=108900.0000
	Stage=         SecondStage     Cost=-218250.0000
	Total scenario cost=-109350.0000

	Name=BelowAverageScenario
	Probability=0.3333
	Leaf Node=BelowAverageNode
	Tree node sequence:
		RootNode
		BelowAverageNode
	Stage=          FirstStage     Cost=108900.0000
	Stage=         SecondStage     Cost=-157720.0000
	Total scenario cost=-48820.0000

----------------------------------------------------

Total EF execution time=0.03 seconds
```
## Probabilistic based in nodes
runef -m farmer-prob -i farmer-prob/nodedata --solver=cplex --solve

Output:
```sh

Initializing extensive form algorithm for stochastic programming problems.
EF solve completed and solution status is optimal
EF solve termination condition is optimal
EF objective: -108390.00001
EF gap:            0.00000
EF bound:     -108390.00001

Extensive form solution:
----------------------------------------------------
Tree Nodes:

	Name=AboveAverageNode
	Stage=SecondStage
	Parent=RootNode
	Variables: 
		QuantitySubQuotaSold[CORN]=48.0
		QuantitySubQuotaSold[SUGAR_BEETS]=6000.0
		QuantitySubQuotaSold[WHEAT]=310.0

	Name=AverageNode
	Stage=SecondStage
	Parent=RootNode
	Variables: 
		QuantitySubQuotaSold[SUGAR_BEETS]=5000.0
		QuantitySubQuotaSold[WHEAT]=225.0

	Name=BelowAverageNode
	Stage=SecondStage
	Parent=RootNode
	Variables: 
		QuantityPurchased[CORN]=48.0
		QuantitySubQuotaSold[SUGAR_BEETS]=4000.0
		QuantitySubQuotaSold[WHEAT]=140.0

	Name=RootNode
	Stage=FirstStage
	Parent=None
	Variables: 
		DevotedAcreage[CORN]=80.0
		DevotedAcreage[SUGAR_BEETS]=250.0
		DevotedAcreage[WHEAT]=170.0


Extensive form costs:
Scenario Tree Costs
----------------------------------------------------
Tree Nodes:

	Name=AboveAverageNode
	Stage=SecondStage
	Parent=RootNode
	Conditional probability=0.3333
	Children:
		None
	Scenarios:
		AboveAverageScenario
	Expected cost of (sub)tree rooted at node=-275900.0000

	Name=AverageNode
	Stage=SecondStage
	Parent=RootNode
	Conditional probability=0.3333
	Children:
		None
	Scenarios:
		AverageScenario
	Expected cost of (sub)tree rooted at node=-218250.0000

	Name=BelowAverageNode
	Stage=SecondStage
	Parent=RootNode
	Conditional probability=0.3333
	Children:
		None
	Scenarios:
		BelowAverageScenario
	Expected cost of (sub)tree rooted at node=-157720.0000

	Name=RootNode
	Stage=FirstStage
	Parent=None
	Conditional probability=1.0000
	Children:
		AboveAverageNode
		AverageNode
		BelowAverageNode
	Scenarios:
		AboveAverageScenario
		AverageScenario
		BelowAverageScenario
	Expected cost of (sub)tree rooted at node=-108390.0000

----------------------------------------------------
Scenarios:

	Name=AboveAverageScenario
	Probability=0.3333
	Leaf Node=AboveAverageNode
	Tree node sequence:
		RootNode
		AboveAverageNode
	Stage=          FirstStage     Cost=108900.0000
	Stage=         SecondStage     Cost=-275900.0000
	Total scenario cost=-167000.0000

	Name=AverageScenario
	Probability=0.3333
	Leaf Node=AverageNode
	Tree node sequence:
		RootNode
		AverageNode
	Stage=          FirstStage     Cost=108900.0000
	Stage=         SecondStage     Cost=-218250.0000
	Total scenario cost=-109350.0000

	Name=BelowAverageScenario
	Probability=0.3333
	Leaf Node=BelowAverageNode
	Tree node sequence:
		RootNode
		BelowAverageNode
	Stage=          FirstStage     Cost=108900.0000
	Stage=         SecondStage     Cost=-157720.0000
	Total scenario cost=-48820.0000

----------------------------------------------------

Total EF execution time=0.04 seconds
```
## Installation of mpi-sppy

conda install openmpi; conda install mpi4py
pip install mpi-sppy
python farmer_ef.py 1 3 cplex

```sh
[    0.00] Initializing mpi-sppy

Welcome to IBM(R) ILOG(R) CPLEX(R) Interactive Optimizer 22.1.0.0
  with Simplex, Mixed Integer & Barrier Optimizers
5725-A06 5725-A29 5724-Y48 5724-Y49 5724-Y54 5724-Y55 5655-Y21
Copyright IBM Corp. 1988, 2022.  All Rights Reserved.

Type 'help' for a list of available commands.
Type 'help' followed by a command name for more
information on commands.

CPLEX> Logfile 'cplex.log' closed.
Logfile '/tmp/tmp249rcqm6.cplex.log' open.
CPLEX> Problem '/tmp/tmps8c90kbr.pyomo.lp' read.
Read time = 0.00 sec. (0.00 ticks)
CPLEX> Problem name         : /tmp/tmps8c90kbr.pyomo.lp
Objective sense      : Minimize
Variables            :      36  [Nneg: 27,  Box: 9]
Objective nonzeros   :      30
Linear constraints   :      45  [Less: 21,  Greater: 18,  Equal: 6]
  Nonzeros           :     102
  RHS nonzeros       :      18

Variables            : Min LB: 0.000000         Max UB: 500.0000       
Objective nonzeros   : Min   : 3.333333         Max   : 33333.33       
Linear constraints   :
  Nonzeros           : Min   : 1.000000         Max   : 24.00000       
  RHS nonzeros       : Min   : 200.0000         Max   : 100000.0       
CPLEX> Version identifier: 22.1.0.0 | 2022-03-09 | 1a383f8ce
Tried aggregator 1 time.
LP Presolve eliminated 20 rows and 6 columns.
Aggregator did 6 substitutions.
Reduced LP has 19 rows, 24 columns, and 54 nonzeros.
Presolve time = 0.00 sec. (0.05 ticks)

Iteration log . . .
Iteration:     1   Scaled dual infeas =           106.666667
Iteration:     4   Dual objective     =     -27139200.000000

Dual simplex - Optimal:  Objective = -1.0839000000e+05
Solution time =    0.00 sec.  Iterations = 14 (3)
Deterministic time = 0.09 ticks  (89.88 ticks/sec)

CPLEX> Solution written to file '/tmp/tmpr_0s0_6c.cplex.sol'.
CPLEX> EF objective: -108390.0

```
