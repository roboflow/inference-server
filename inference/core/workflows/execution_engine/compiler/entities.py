from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Set, Type, Union

import networkx as nx

from inference.core.workflows.entities.base import InputType, JsonField
from inference.core.workflows.prototypes.block import (
    WorkflowBlock,
    WorkflowBlockManifest,
)


@dataclass(frozen=True)
class BlockSpecification:
    block_source: str
    identifier: str
    block_class: Type[WorkflowBlock]
    manifest_class: Type[WorkflowBlockManifest]


@dataclass(frozen=True)
class InitialisedStep:
    block_specification: BlockSpecification
    manifest: WorkflowBlockManifest
    step: WorkflowBlock


@dataclass(frozen=True)
class ParsedWorkflowDefinition:
    version: str
    inputs: List[InputType]
    steps: List[WorkflowBlockManifest]
    outputs: List[JsonField]


@dataclass(frozen=True)
class InputSubstitution:
    input_parameter_name: str
    step_manifest: WorkflowBlockManifest
    manifest_property: str


@dataclass(frozen=True)
class CompiledWorkflow:
    workflow_definition: ParsedWorkflowDefinition
    execution_graph: nx.DiGraph
    steps: Dict[str, InitialisedStep]
    input_substitutions: List[InputSubstitution]


class NodeCategory(Enum):
    INPUT_NODE = "INPUT_NODE"
    STEP_NODE = "STEP_NODE"
    OUTPUT_NODE = "OUTPUT_NODE"


@dataclass
class ExecutionGraphNode:
    node_category: NodeCategory
    name: str
    selector: str
    data_lineage: List[str]


@dataclass
class InputNode(ExecutionGraphNode):
    input_manifest: InputType

    @property
    def dimensionality(self) -> int:
        return len(self.data_lineage)

    def is_batch_oriented(self) -> bool:
        return len(self.data_lineage) > 0


@dataclass
class OutputNode(ExecutionGraphNode):
    output_manifest: JsonField

    @property
    def dimensionality(self) -> int:
        return len(self.data_lineage)

    def is_batch_oriented(self) -> bool:
        return len(self.data_lineage) > 0


class NodeInputCategory(Enum):
    NON_BATCH_INPUT_PARAMETER = "NON_BATCH_INPUT_PARAMETER"
    BATCH_INPUT_PARAMETER = "BATCH_INPUT_PARAMETER"
    NON_BATCH_STEP_OUTPUT = "NON_BATCH_STEP_OUTPUT"
    BATCH_STEP_OUTPUT = "BATCH_STEP_OUTPUT"
    STATIC_VALUE = "STATIC_VALUE"


INPUTS_REFERENCES = {
    NodeInputCategory.NON_BATCH_INPUT_PARAMETER,
    NodeInputCategory.BATCH_INPUT_PARAMETER,
}
STEPS_OUTPUTS_REFERENCES = {
    NodeInputCategory.NON_BATCH_STEP_OUTPUT,
    NodeInputCategory.BATCH_STEP_OUTPUT,
}


@dataclass(frozen=True)
class StepInputDefinition:
    name: str
    category: NodeInputCategory

    def points_to_input(self) -> bool:
        return self.category in INPUTS_REFERENCES

    def points_to_step_output(self) -> bool:
        return self.category in STEPS_OUTPUTS_REFERENCES

    def is_static_value(self) -> bool:
        return self.category is NodeInputCategory.STATIC_VALUE

    @abstractmethod
    def is_batch_oriented(self) -> bool:
        pass

    @classmethod
    def is_compound_input(cls) -> bool:
        return False


@dataclass(frozen=True)
class DynamicStepInputDefinition(StepInputDefinition):
    data_lineage: List[str]
    selector: str

    def is_batch_oriented(self) -> bool:
        return len(self.data_lineage) > 0

    @property
    def dimensionality(self) -> int:
        return len(self.data_lineage)


@dataclass(frozen=True)
class StaticStepInputDefinition(StepInputDefinition):
    value: Any

    def is_batch_oriented(self) -> bool:
        return False


@dataclass(frozen=True)
class CompoundDynamicStepInputDefinition:
    name: str
    nested_definitions: Union[
        List[StepInputDefinition], Dict[str, StaticStepInputDefinition]
    ]

    @classmethod
    def is_compound_input(cls) -> bool:
        return True

    def represents_list_of_inputs(self) -> bool:
        return isinstance(self.nested_definitions, list)


@dataclass(frozen=True)
class ListOfDynamicStepInputDefinition(CompoundDynamicStepInputDefinition):
    nested_definitions: List[StepInputDefinition]


@dataclass(frozen=True)
class DictOfDynamicStepInputDefinition(CompoundDynamicStepInputDefinition):
    nested_definitions: Dict[
        str, Union[StaticStepInputDefinition, DynamicStepInputDefinition]
    ]


@dataclass
class StepNode(ExecutionGraphNode):
    step_manifest: WorkflowBlockManifest
    input_data: Dict[
        str,
        Union[
            DynamicStepInputDefinition,
            StaticStepInputDefinition,
            CompoundDynamicStepInputDefinition,
        ],
    ] = field(default_factory=dict)
    dimensionality_reference_property: Optional[str] = None
    child_execution_branches: Dict[str, str] = field(default_factory=dict)
    execution_branches_impacting_inputs: Set[str] = field(default_factory=set)

    # def is_simd_step(self) -> bool:
    #     for input_definition in self.input_data.values():
    #         if not input_definition.is_compound_input():
    #             if input_definition.is_batch_oriented():
    #                 return True
    #         nested_elements = input_definition.nested_definitions
    #         if not input_definition.represents_list_of_inputs():
    #             nested_elements = nested_elements.values()
    #         for nested_element in nested_elements:
    #             if nested_element.is_compound_input():
    #                 raise ValueError(
    #                     f"While examining the nature of step `{self.name}` input `{input_definition.name}` "
    #                     f" discovered inputs nesting beyond supported nesting levels."
    #                 )
    #             if nested_element.is_batch_oriented():
    #                 return True
    #     return False

    def controls_flow(self) -> bool:
        if self.child_execution_branches:
            return True
        return False

    @property
    def output_dimensionality(self) -> int:
        return len(self.data_lineage)
