import abc
from collections import defaultdict
from queue import Queue
from typing import List, Optional, Set

import networkx as nx
from networkx import DiGraph

from inference.core.workflows.constants import STEP_NODE_KIND
from inference.core.workflows.entities.types import FlowControl
from inference.core.workflows.errors import InvalidBlockBehaviourError
from inference.core.workflows.execution_engine.compiler.graph_constructor import (
    assign_max_distances_from_start,
    group_nodes_by_sorted_key_value,
)
from inference.core.workflows.execution_engine.compiler.utils import (
    get_nodes_of_specific_kind,
)


class StepExecutionCoordinator(metaclass=abc.ABCMeta):

    @classmethod
    @abc.abstractmethod
    def init(cls, execution_graph: nx.DiGraph) -> "StepExecutionCoordinator":
        pass

    @abc.abstractmethod
    def get_steps_to_execute_next(
        self, steps_to_discard: Set[str]
    ) -> Optional[List[str]]:
        pass


class ParallelStepExecutionCoordinator(StepExecutionCoordinator):

    @classmethod
    def init(cls, execution_graph: nx.DiGraph) -> "StepExecutionCoordinator":
        return cls(execution_graph=execution_graph)

    def __init__(self, execution_graph: nx.DiGraph):
        self._execution_graph = execution_graph.copy()
        self._discarded_steps: Set[str] = set()
        self.__execution_order: Optional[List[List[str]]] = None
        self.__execution_pointer = 0

    def get_steps_to_execute_next(
        self, steps_to_discard: Set[str]
    ) -> Optional[List[str]]:
        if self.__execution_order is None:
            self.__execution_order = establish_execution_order(
                execution_graph=self._execution_graph
            )
            self.__execution_pointer = 0
        self._discarded_steps.update(steps_to_discard)
        next_step = None
        while self.__execution_pointer < len(self.__execution_order):
            candidate_steps = [
                e
                for e in self.__execution_order[self.__execution_pointer]
                if e not in self._discarded_steps
            ]
            self.__execution_pointer += 1
            if len(candidate_steps) == 0:
                continue
            return candidate_steps
        return next_step


def establish_execution_order(
    execution_graph: nx.DiGraph,
) -> List[List[str]]:
    start_node, end_node = "start", "end"
    steps_flow_graph = construct_steps_flow_graph(
        execution_graph=execution_graph,
        start_node=start_node,
        end_node=end_node,
    )
    distance_key = "distance"
    steps_flow_graph = assign_max_distances_from_start(
        graph=steps_flow_graph,
        start_node="start",
        distance_key=distance_key,
    )
    return group_nodes_by_sorted_key_value(
        graph=steps_flow_graph,
        excluded_nodes={start_node, end_node},
        key=distance_key,
    )


def construct_steps_flow_graph(
    execution_graph: nx.DiGraph,
    start_node: str,
    end_node: str,
) -> nx.DiGraph:
    steps_flow_graph = nx.DiGraph()
    steps_flow_graph.add_node(start_node)
    steps_flow_graph.add_node(end_node)
    step_nodes = get_nodes_of_specific_kind(
        execution_graph=execution_graph, kind=STEP_NODE_KIND
    )
    for step_node in step_nodes:
        has_predecessors = False
        for predecessor in execution_graph.predecessors(step_node):
            start_node = predecessor if predecessor in step_nodes else step_node
            steps_flow_graph.add_edge(start_node, step_node)
            has_predecessors = True
        if not has_predecessors:
            steps_flow_graph.add_edge(start_node, step_node)
        has_successors = False
        for successor in execution_graph.successors(step_node):
            end_node = successor if successor in step_nodes else end_node
            steps_flow_graph.add_edge(step_node, end_node)
            has_successors = True
        if not has_successors:
            steps_flow_graph.add_edge(step_node, end_node)
    return steps_flow_graph


def get_next_steps_to_execute(
    execution_order: List[List[str]],
    execution_pointer: int,
    discarded_steps: Set[str],
) -> List[str]:
    return [e for e in execution_order[execution_pointer] if e not in discarded_steps]


def handle_flow_control(
    current_step_selector: str,
    flow_control: FlowControl,
    execution_graph: nx.DiGraph,
) -> Set[str]:
    nodes_to_discard = set()
    if flow_control.mode == "terminate_branch":
        nodes_to_discard = get_all_nodes_in_execution_path(
            execution_graph=execution_graph,
            source=current_step_selector,
            include_source=False,
        )
    elif flow_control.mode == "select_step":
        nodes_to_discard = handle_execution_branch_selection(
            current_step=current_step_selector,
            execution_graph=execution_graph,
            selected_next_step=flow_control.context,
        )
    return nodes_to_discard


def handle_execution_branch_selection(
    current_step: str,
    execution_graph: nx.DiGraph,
    selected_next_step: Optional[str],
) -> Set[str]:
    nodes_to_discard = set()
    if not execution_graph.has_node(selected_next_step):
        raise InvalidBlockBehaviourError(
            public_message=f"Block implementing step {current_step} requested flow control "
            f"mode `select_step`, but selected next step as: {selected_next_step} - which"
            f"is not a step that exists in workflow.",
            context="workflow_execution | flow_control_coordination",
        )
    for neighbour in execution_graph.neighbors(current_step):
        if execution_graph.nodes[neighbour].get("kind") != STEP_NODE_KIND:
            continue
        if neighbour == selected_next_step:
            continue
        neighbour_execution_path = get_all_nodes_in_execution_path(
            execution_graph=execution_graph, source=neighbour
        )
        nodes_to_discard.update(neighbour_execution_path)
    return nodes_to_discard


def get_all_nodes_in_execution_path(
    execution_graph: DiGraph, source: str, include_source: bool = True
) -> Set[str]:
    nodes = set(nx.descendants(execution_graph, source))
    if include_source:
        nodes.add(source)
    return nodes
