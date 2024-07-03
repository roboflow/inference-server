import numpy as np
import pytest

from inference.core.env import WORKFLOWS_MAX_CONCURRENT_STEPS
from inference.core.managers.base import ModelManager
from inference.core.workflows.core_steps.common.entities import StepExecutionMode
from inference.core.workflows.errors import StepOutputLineageError
from inference.core.workflows.execution_engine.core import ExecutionEngine

WORKFLOW_WITH_EXTRACTION_OF_CLASSES_FOR_DETECTIONS = {
    "version": "1.0",
    "inputs": [
        {"type": "WorkflowImage", "name": "image"},
        {"type": "WorkflowParameter", "name": "reference"},
    ],
    "steps": [
        {
            "type": "ObjectDetectionModel",
            "name": "general_detection",
            "image": "$inputs.image",
            "model_id": "yolov8n-640",
        },
        {
            "type": "PropertyExtraction",
            "name": "property_extraction",
            "data": "$steps.general_detection.predictions",
            "operations": [
                {"type": "DetectionsPropertyExtract", "property_name": "class_name"}
            ],
        },
        {
            "type": "PropertyExtraction",
            "name": "instances_counter",
            "data": "$steps.general_detection.predictions",
            "operations": [{"type": "SequenceLength"}],
        },
        {
            "type": "Expression",
            "name": "expression",
            "data": {
                "class_names": "$steps.property_extraction.output",
                "reference": "$inputs.reference",
            },
            "switch": {
                "type": "CasesDefinition",
                "cases": [
                    {
                        "type": "CaseDefinition",
                        "condition": {
                            "type": "StatementGroup",
                            "statements": [
                                {
                                    "type": "BinaryStatement",
                                    "left_operand": {
                                        "type": "DynamicOperand",
                                        "operand_name": "class_names",
                                    },
                                    "comparator": {"type": "=="},
                                    "right_operand": {
                                        "type": "DynamicOperand",
                                        "operand_name": "reference",
                                    },
                                }
                            ],
                        },
                        "result": {"type": "StaticCaseResult", "value": "PASS"},
                    }
                ],
                "default": {"type": "StaticCaseResult", "value": "FAIL"},
            },
        },
    ],
    "outputs": [
        {
            "type": "JsonField",
            "name": "detected_classes",
            "selector": "$steps.property_extraction.output",
        },
        {
            "type": "JsonField",
            "name": "number_of_detected_boxes",
            "selector": "$steps.instances_counter.output",
        },
        {
            "type": "JsonField",
            "name": "verdict",
            "selector": "$steps.expression.output",
        },
    ],
}


@pytest.mark.asyncio
async def test_workflow_with_extraction_of_classes_for_detections(
    model_manager: ModelManager,
    dogs_image: np.ndarray,
    crowd_image: np.ndarray,
    roboflow_api_key: str,
) -> None:
    # given
    workflow_init_parameters = {
        "workflows_core.model_manager": model_manager,
        "workflows_core.api_key": roboflow_api_key,
        "workflows_core.step_execution_mode": StepExecutionMode.LOCAL,
    }
    execution_engine = ExecutionEngine.init(
        workflow_definition=WORKFLOW_WITH_EXTRACTION_OF_CLASSES_FOR_DETECTIONS,
        init_parameters=workflow_init_parameters,
        max_concurrent_steps=WORKFLOWS_MAX_CONCURRENT_STEPS,
    )

    # when
    result = await execution_engine.run_async(
        runtime_parameters={
            "image": [dogs_image, crowd_image],
            "reference": ["dog", "dog"],
        }
    )

    assert isinstance(result, list), "Expected list to be delivered"
    assert len(result) == 2, "Expected 2 elements in the output for two input images"
    assert set(result[0].keys()) == {
        "detected_classes",
        "verdict",
        "number_of_detected_boxes",
    }, "Expected all declared outputs to be delivered"
    assert set(result[1].keys()) == {
        "detected_classes",
        "verdict",
        "number_of_detected_boxes",
    }, "Expected all declared outputs to be delivered"
    assert result[0]["detected_classes"] == [
        "dog",
        "dog",
    ], "Expected two instances of dogs found in first image"
    assert (
        result[0]["verdict"] == "PASS"
    ), "Expected first image to match expected classes"
    assert (
        result[0]["number_of_detected_boxes"] == 2
    ), "Expected 2 dogs detected in first image"
    assert (
        result[1]["detected_classes"] == ["person"] * 12
    ), "Expected 12 instances of person found in second image"
    assert (
        result[1]["verdict"] == "FAIL"
    ), "Expected second image not to match expected classes"
    assert (
        result[1]["number_of_detected_boxes"] == 12
    ), "Expected 12 people detected in second image"


WORKFLOW_WITH_EXTRACTION_OF_CLASS_NAME_FROM_CROPS_AND_CONCATENATION_OF_RESULTS = {
    "version": "1.0",
    "inputs": [
        {"type": "WorkflowImage", "name": "image"},
        {"type": "WorkflowParameter", "name": "reference"},
    ],
    "steps": [
        {
            "type": "ObjectDetectionModel",
            "name": "general_detection",
            "image": "$inputs.image",
            "model_id": "yolov8n-640",
            "class_filter": ["dog"],
        },
        {
            "type": "Crop",
            "name": "cropping",
            "image": "$inputs.image",
            "predictions": "$steps.general_detection.predictions",
        },
        {
            "type": "ClassificationModel",
            "name": "breds_classification",
            "image": "$steps.cropping.crops",
            "model_id": "dog-breed-xpaq6/1",
        },
        {
            "type": "PropertyExtraction",
            "name": "property_extraction",
            "data": "$steps.breds_classification.predictions",
            "operations": [
                {"type": "ClassificationPropertyExtract", "property_name": "top_class"}
            ],
        },
        {
            "type": "DimensionCollapse",
            "name": "outputs_concatenation",
            "data": "$steps.property_extraction.output",
        },
        {
            "type": "FirstNonEmptyOrDefault",
            "name": "empty_values_replacement",
            "data": ["$steps.outputs_concatenation.output"],
            "default": [],
        },
        {
            "type": "Expression",
            "name": "expression",
            "data": {
                "detected_classes": "$steps.empty_values_replacement.output",
                "reference": "$inputs.reference",
            },
            "switch": {
                "type": "CasesDefinition",
                "cases": [
                    {
                        "type": "CaseDefinition",
                        "condition": {
                            "type": "StatementGroup",
                            "statements": [
                                {
                                    "type": "BinaryStatement",
                                    "left_operand": {
                                        "type": "DynamicOperand",
                                        "operand_name": "detected_classes",
                                    },
                                    "comparator": {"type": "=="},
                                    "right_operand": {
                                        "type": "DynamicOperand",
                                        "operand_name": "reference",
                                    },
                                }
                            ],
                        },
                        "result": {"type": "StaticCaseResult", "value": "PASS"},
                    }
                ],
                "default": {"type": "StaticCaseResult", "value": "FAIL"},
            },
        },
    ],
    "outputs": [
        {
            "type": "JsonField",
            "name": "detected_classes",
            "selector": "$steps.property_extraction.output",
        },
        {
            "type": "JsonField",
            "name": "wrapped_classes",
            "selector": "$steps.empty_values_replacement.output",
        },
        {
            "type": "JsonField",
            "name": "verdict",
            "selector": "$steps.expression.output",
        },
    ],
}


@pytest.mark.asyncio
async def test_workflow_with_extraction_of_classes_for_classification_on_crops(
    model_manager: ModelManager,
    dogs_image: np.ndarray,
    crowd_image: np.ndarray,
    roboflow_api_key: str,
) -> None:
    # given
    workflow_init_parameters = {
        "workflows_core.model_manager": model_manager,
        "workflows_core.api_key": roboflow_api_key,
        "workflows_core.step_execution_mode": StepExecutionMode.LOCAL,
    }
    execution_engine = ExecutionEngine.init(
        workflow_definition=WORKFLOW_WITH_EXTRACTION_OF_CLASS_NAME_FROM_CROPS_AND_CONCATENATION_OF_RESULTS,
        init_parameters=workflow_init_parameters,
        max_concurrent_steps=WORKFLOWS_MAX_CONCURRENT_STEPS,
    )

    # when
    result = await execution_engine.run_async(
        runtime_parameters={
            "image": [dogs_image, crowd_image],
            "reference": [
                "116.Parson_russell_terrier",
                "131.Wirehaired_pointing_griffon",
            ],
        }
    )

    assert isinstance(result, list), "Expected list to be delivered"
    assert len(result) == 2, "Expected 2 elements in the output for two input images"
    assert set(result[0].keys()) == {
        "detected_classes",
        "wrapped_classes",
        "verdict",
    }, "Expected all declared outputs to be delivered"
    assert set(result[1].keys()) == {
        "detected_classes",
        "wrapped_classes",
        "verdict",
    }, "Expected all declared outputs to be delivered"
    assert result[0]["detected_classes"] == [
        "116.Parson_russell_terrier",
        "131.Wirehaired_pointing_griffon",
    ], "Expected two instances of dogs found in first image"
    assert result[0]["wrapped_classes"] == [
        "116.Parson_russell_terrier",
        "131.Wirehaired_pointing_griffon",
    ], "Expected two instances of dogs found in first image"
    assert (
        result[0]["verdict"] == "PASS"
    ), "Expected first image to match expected classes"
    assert (
        result[1]["detected_classes"] == []
    ), "Expected no instances of dogs found in second image"
    assert (
        result[1]["wrapped_classes"] == []
    ), "Expected no instances of dogs found in second image"
    assert (
        result[1]["verdict"] == "FAIL"
    ), "Expected second image not to match expected classes"


WORKFLOW_PERFORMING_OCR_AND_AGGREGATION_TO_PERFORM_PASS_FAIL_FOR_ALL_PLATES_FOUND_IN_IMAGE_AT_ONCE = {
    "version": "1.0",
    "inputs": [
        {"type": "WorkflowImage", "name": "image"},
        {"type": "WorkflowParameter", "name": "reference"},
    ],
    "steps": [
        {
            "type": "RoboflowObjectDetectionModel",
            "name": "plates_detection",
            "image": "$inputs.image",
            "model_id": "vehicle-registration-plates-trudk/2",
        },
        {
            "type": "DetectionOffset",
            "name": "plates_offset",
            "predictions": "$steps.plates_detection.predictions",
            "offset_width": 50,
            "offset_height": 50,
        },
        {
            "type": "Crop",
            "name": "plates_crops",
            "image": "$inputs.image",
            "predictions": "$steps.plates_offset.predictions",
        },
        {
            "type": "OCRModel",
            "name": "ocr",
            "image": "$steps.plates_crops.crops",
        },
        {
            "type": "DimensionCollapse",
            "name": "outputs_concatenation",
            "data": "$steps.ocr.result",
        },
        {
            "type": "FirstNonEmptyOrDefault",
            "name": "empty_values_replacement",
            "data": ["$steps.outputs_concatenation.output"],
            "default": [],
        },
        {
            "type": "Expression",
            "name": "expression",
            "data": {
                "outputs_concatenation": "$steps.empty_values_replacement.output",
                "reference": "$inputs.reference",
            },
            "data_operations": {
                "outputs_concatenation": [{"type": "SequenceLength"}],
            },
            "switch": {
                "type": "CasesDefinition",
                "cases": [
                    {
                        "type": "CaseDefinition",
                        "condition": {
                            "type": "StatementGroup",
                            "statements": [
                                {
                                    "type": "BinaryStatement",
                                    "left_operand": {
                                        "type": "DynamicOperand",
                                        "operand_name": "outputs_concatenation",
                                    },
                                    "comparator": {"type": "=="},
                                    "right_operand": {
                                        "type": "DynamicOperand",
                                        "operand_name": "reference",
                                    },
                                }
                            ],
                        },
                        "result": {"type": "StaticCaseResult", "value": "PASS"},
                    }
                ],
                "default": {"type": "StaticCaseResult", "value": "FAIL"},
            },
        },
    ],
    "outputs": [
        {"type": "JsonField", "name": "plates_ocr", "selector": "$steps.ocr.result"},
        {
            "type": "JsonField",
            "name": "concatenated_ocr",
            "selector": "$steps.empty_values_replacement.output",
        },
        {
            "type": "JsonField",
            "name": "verdict",
            "selector": "$steps.expression.output",
        },
    ],
}


@pytest.mark.asyncio
async def test_workflow_with_aggregation_of_ocr_results_globally_for_image(
    model_manager: ModelManager,
    license_plate_image: np.ndarray,
    roboflow_api_key: str,
) -> None:
    # given
    workflow_init_parameters = {
        "workflows_core.model_manager": model_manager,
        "workflows_core.api_key": roboflow_api_key,
        "workflows_core.step_execution_mode": StepExecutionMode.LOCAL,
    }
    execution_engine = ExecutionEngine.init(
        workflow_definition=WORKFLOW_PERFORMING_OCR_AND_AGGREGATION_TO_PERFORM_PASS_FAIL_FOR_ALL_PLATES_FOUND_IN_IMAGE_AT_ONCE,
        init_parameters=workflow_init_parameters,
        max_concurrent_steps=WORKFLOWS_MAX_CONCURRENT_STEPS,
    )

    # when
    result = await execution_engine.run_async(
        runtime_parameters={
            "image": license_plate_image,
            "reference": 2,
        }
    )

    # then
    assert isinstance(result, list), "Expected list to be delivered"
    assert len(result) == 1, "Expected 1 elements in the output for one input image"
    assert set(result[0].keys()) == {
        "plates_ocr",
        "concatenated_ocr",
        "verdict",
    }, "Expected all declared outputs to be delivered"
    assert (
        isinstance(result[0]["plates_ocr"], list) and len(result[0]["plates_ocr"]) == 2
    ), "Expected 2 plates to be found"
    # In this case, output does not reveal the concatenation result, but we could not make expression without concat
    assert (
        isinstance(result[0]["concatenated_ocr"], list)
        and len(result[0]["concatenated_ocr"]) == 2
    ), "Expected 2 plates to be found"
    assert result[0]["verdict"] == "PASS", "Expected to meet the condition"


WORKFLOW_PERFORMING_OCR_AND_AGGREGATION_TO_PERFORM_PASS_FAIL_FOR_EACH_PLATE_SEPARATELY = {
    "version": "1.0",
    "inputs": [
        {"type": "WorkflowImage", "name": "image"},
        {"type": "WorkflowParameter", "name": "reference"},
    ],
    "steps": [
        {
            "type": "RoboflowObjectDetectionModel",
            "name": "plates_detection",
            "image": "$inputs.image",
            "model_id": "vehicle-registration-plates-trudk/2",
        },
        {
            "type": "DetectionOffset",
            "name": "plates_offset",
            "predictions": "$steps.plates_detection.predictions",
            "offset_width": 50,
            "offset_height": 50,
        },
        {
            "type": "Crop",
            "name": "plates_crops",
            "image": "$inputs.image",
            "predictions": "$steps.plates_offset.predictions",
        },
        {
            "type": "OCRModel",
            "name": "ocr",
            "image": "$steps.plates_crops.crops",
        },
        {
            "type": "Expression",
            "name": "expression",
            "data": {
                "outputs_concatenation": "$steps.ocr.result",
                "reference": "$inputs.reference",
            },
            "data_operations": {
                "outputs_concatenation": [{"type": "SequenceLength"}],
            },
            "switch": {
                "type": "CasesDefinition",
                "cases": [
                    {
                        "type": "CaseDefinition",
                        "condition": {
                            "type": "StatementGroup",
                            "statements": [
                                {
                                    "type": "BinaryStatement",
                                    "left_operand": {
                                        "type": "DynamicOperand",
                                        "operand_name": "outputs_concatenation",
                                    },
                                    "comparator": {"type": "(Number) >"},
                                    "right_operand": {
                                        "type": "DynamicOperand",
                                        "operand_name": "reference",
                                    },
                                }
                            ],
                        },
                        "result": {"type": "StaticCaseResult", "value": "PASS"},
                    }
                ],
                "default": {"type": "StaticCaseResult", "value": "FAIL"},
            },
        },
    ],
    "outputs": [
        {"type": "JsonField", "name": "plates_ocr", "selector": "$steps.ocr.result"},
        {
            "type": "JsonField",
            "name": "verdict",
            "selector": "$steps.expression.output",
        },
    ],
}


@pytest.mark.asyncio
async def test_workflow_with_pass_fail_applied_for_each_ocr_result(
    model_manager: ModelManager,
    license_plate_image: np.ndarray,
    dogs_image: np.ndarray,
    roboflow_api_key: str,
) -> None:
    # given
    workflow_init_parameters = {
        "workflows_core.model_manager": model_manager,
        "workflows_core.api_key": roboflow_api_key,
        "workflows_core.step_execution_mode": StepExecutionMode.LOCAL,
    }
    execution_engine = ExecutionEngine.init(
        workflow_definition=WORKFLOW_PERFORMING_OCR_AND_AGGREGATION_TO_PERFORM_PASS_FAIL_FOR_EACH_PLATE_SEPARATELY,
        init_parameters=workflow_init_parameters,
        max_concurrent_steps=WORKFLOWS_MAX_CONCURRENT_STEPS,
    )

    # when
    result = await execution_engine.run_async(
        runtime_parameters={
            "image": [license_plate_image, dogs_image],
            "reference": 0,
        }
    )

    # then
    assert isinstance(result, list), "Expected list to be delivered"
    assert len(result) == 2, "Expected 2 elements in the output for two input images"
    assert set(result[0].keys()) == {
        "plates_ocr",
        "verdict",
    }, "Expected all declared outputs to be delivered"
    assert set(result[1].keys()) == {
        "plates_ocr",
        "verdict",
    }, "Expected all declared outputs to be delivered"
    assert (
        isinstance(result[0]["plates_ocr"], list) and len(result[0]["plates_ocr"]) == 2
    ), "Expected 2 plates to be found in first image"
    assert (
        isinstance(result[0]["verdict"], list) and len(result[0]["verdict"]) == 2
    ), "Expected verdict for each plate recognised in first image"
    assert result[0]["verdict"][0] in {"PASS", "FAIL"}, "Expected valid verdict"
    assert result[0]["verdict"][1] in {"PASS", "FAIL"}, "Expected valid verdict"
    assert (
        isinstance(result[1]["plates_ocr"], list) and len(result[1]["plates_ocr"]) == 0
    ), "Expected 0 plates to be found in second image"
    assert (
        isinstance(result[1]["verdict"], list) and len(result[1]["verdict"]) == 0
    ), "Expected 0 verdicts to be given in second image"


WORKFLOW_WITH_INVALID_AGGREGATION = {
    "version": "1.0",
    "inputs": [
        {"type": "WorkflowImage", "name": "image"},
    ],
    "steps": [
        {
            "type": "RoboflowObjectDetectionModel",
            "name": "plates_detection",
            "image": "$inputs.image",
            "model_id": "vehicle-registration-plates-trudk/2",
        },
        {
            "type": "DimensionCollapse",
            "name": "invalid_concatenation",
            "data": "$steps.plates_detection.predictions",
        },
    ],
    "outputs": [
        {
            "type": "JsonField",
            "name": "result",
            "selector": "$steps.invalid_concatenation.output",
        },
    ],
}


@pytest.mark.asyncio
async def test_workflow_when_there_is_faulty_application_of_aggregation_step_at_batch_with_dimension_1(
    model_manager: ModelManager,
    license_plate_image: np.ndarray,
    roboflow_api_key: str,
) -> None:
    # given
    workflow_init_parameters = {
        "workflows_core.model_manager": model_manager,
        "workflows_core.api_key": roboflow_api_key,
        "workflows_core.step_execution_mode": StepExecutionMode.LOCAL,
    }

    # when
    with pytest.raises(StepOutputLineageError):
        _ = ExecutionEngine.init(
            workflow_definition=WORKFLOW_WITH_INVALID_AGGREGATION,
            init_parameters=workflow_init_parameters,
            max_concurrent_steps=WORKFLOWS_MAX_CONCURRENT_STEPS,
        )
