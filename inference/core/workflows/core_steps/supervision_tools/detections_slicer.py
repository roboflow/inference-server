import pickle
from typing import Any, Dict, List, Literal, Optional, Type, Union
from pydantic import ConfigDict, Field, PositiveInt
import numpy as np
import supervision as sv

from inference.core.entities.requests.inference import (
    ObjectDetectionInferenceRequest,
)
from inference.core.entities.responses.inference import InferenceResponseImage, ObjectDetectionInferenceResponse, ObjectDetectionPrediction
from inference.core.env import (
    HOSTED_CLASSIFICATION_URL,
    LOCAL_INFERENCE_API_URL,
    WORKFLOWS_REMOTE_API_TARGET,
    WORKFLOWS_REMOTE_EXECUTION_MAX_STEP_BATCH_SIZE,
    WORKFLOWS_REMOTE_EXECUTION_MAX_STEP_CONCURRENT_REQUESTS,
)
from inference.core.utils.image_utils import xyxy_to_xywh
from inference.core.managers.base import ModelManager
from inference.core.workflows.core_steps.common.utils import (
    attach_parents_coordinates_to_batch_of_sv_detections,
    attach_prediction_type_info_to_sv_detections_batch,
    convert_inference_detections_batch_to_sv_detections,
    filter_out_unwanted_classes_from_sv_detections_batch,
)
from inference.core.workflows.entities.base import (
    Batch,
    OutputDefinition,
    WorkflowImageData   
)
from inference.core.workflows.entities.types import (
    BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND,
    BOOLEAN_KIND,
    FLOAT_ZERO_TO_ONE_KIND,
    INTEGER_KIND,
    LIST_OF_VALUES_KIND,
    ROBOFLOW_MODEL_ID_KIND,
    FloatZeroToOne,
    ImageInputField,
    RoboflowModelField,
    StepOutputImageSelector,
    WorkflowImageSelector,
    WorkflowParameterSelector,
)
from inference.core.workflows.prototypes.block import (
    WorkflowBlock,
    WorkflowBlockManifest,
)
from inference_sdk import InferenceConfiguration, InferenceHTTPClient

LONG_DESCRIPTION = """
Instead of running inference on the whole image, first slice it into small segments,
run inference on each ones and merge them together. This helps detect small objects,
and is also known as Slicing Aided Hyper Inference (SAHI).

The model can be any object detection or segmentation model, hosted on or uploaded
to Roboflow. You can query any model that is private to your account, or any public
model available on [Roboflow Universe](https://universe.roboflow.com).

You will need to set your Roboflow API key in your Inference environment to use this 
block. To learn more about setting your Roboflow API key, [refer to the Inference 
documentation](https://inference.roboflow.com/quickstart/configure_api_key/).
"""


class BlockManifest(WorkflowBlockManifest):
    model_config = ConfigDict(
        json_schema_extra={
            "name": "Detections Inference Slicer",
            "short_description": "Run inference on small segments of an image",
            "long_description": LONG_DESCRIPTION,
            "license": "Apache-2.0",
            "block_type": "model",
        },
        protected_namespaces=(),
    )
    type: Literal["RoboflowDetectionsInferenceSlicer", "DetectionsInferenceSlicer"]
    images: Union[WorkflowImageSelector, StepOutputImageSelector] = ImageInputField
    model_id: Union[WorkflowParameterSelector(kind=[ROBOFLOW_MODEL_ID_KIND]), str] = (
        RoboflowModelField
    )

    class_agnostic_nms: Union[
        Optional[bool], WorkflowParameterSelector(kind=[BOOLEAN_KIND])
    ] = Field(
        default=False,
        description="Value to decide if NMS is to be used in class-agnostic mode.",
        examples=[True, "$inputs.class_agnostic_nms"],
    )
    class_filter: Union[
        Optional[List[str]], WorkflowParameterSelector(kind=[LIST_OF_VALUES_KIND])
    ] = Field(
        default=None,
        description="List of classes to retrieve from predictions (to define subset of those which was used while model training)",
        examples=[["a", "b", "c"], "$inputs.class_filter"],
    )
    confidence: Union[
        FloatZeroToOne,
        WorkflowParameterSelector(kind=[FLOAT_ZERO_TO_ONE_KIND]),
    ] = Field(
        default=0.4,
        description="Confidence threshold for predictions",
        examples=[0.3, "$inputs.confidence_threshold"],
    )
    iou_threshold: Union[
        FloatZeroToOne,
        WorkflowParameterSelector(kind=[FLOAT_ZERO_TO_ONE_KIND]),
    ] = Field(
        default=0.3,
        description="Parameter of NMS, to decide on minimum box intersection over union to merge boxes",
        examples=[0.4, "$inputs.iou_threshold"],
    )

    slice_width: Union[
        PositiveInt, WorkflowParameterSelector(kind=[INTEGER_KIND])
    ] = Field(
        default=320,
        description="Width of each slice, in pixels",
        examples=[320, "$inputs.slice_width"],
    )
    slice_height: Union[
        PositiveInt, WorkflowParameterSelector(kind=[INTEGER_KIND])
    ] = Field(
        default=320,
        description="Height of each slice, in pixels",
        examples=[320, "$inputs.slice_height"],
    )
    overlap_ration_width: Union[
        FloatZeroToOne, WorkflowParameterSelector(kind=[FLOAT_ZERO_TO_ONE_KIND])
    ] = Field(
        default=0.2,
        description="Overlap ratio between consecutive slices in the width dimension",
        examples=[0.2, "$inputs.overlap_ratio_width"],
    )
    overlap_ration_height: Union[
        FloatZeroToOne, WorkflowParameterSelector(kind=[FLOAT_ZERO_TO_ONE_KIND])
    ] = Field(
        default=0.2,
        description="Overlap ratio between consecutive slices in the height dimension",
        examples=[0.2, "$inputs.overlap_ratio_height"],
    )

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(
                name="predictions", kind=[BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND],
            )
        ]


class RoboflowDetectionSlicerBlock(WorkflowBlock):
    def __init__(
        self,
        model_manager: ModelManager,
        api_key: Optional[str],
    ):
        self._model_manager = model_manager
        self._api_key = api_key

    @classmethod
    def get_init_parameters(cls) -> List[str]:
        return ["model_manager", "api_key"]

    @classmethod
    def get_manifest(cls) -> Type[WorkflowBlockManifest]:
        return BlockManifest

    async def run_locally(
        self,
        images: Batch[Optional[WorkflowImageData]],
        model_id: str,
        class_agnostic_nms: Optional[bool],
        class_filter: Optional[List[str]],
        confidence: Optional[float],
        iou_threshold: Optional[float],
        slice_width: Optional[int],
        slice_height: Optional[int],
        overlap_ratio_width: Optional[float],
        overlap_ratio_height: Optional[float],
    ) -> List[Dict[str, Union[sv.Detections, Any]]]:
        non_empty_images = [i for i in images.iter_nonempty()]
        non_empty_inference_images = [i.numpy_image for i in non_empty_images]

        self._model_manager.add_model(
            model_id=model_id,
            api_key=self._api_key,
        )
        model = self._model_manager.models()[model_id]

        def slicer_callback(image_slice: np.ndarray):
            inference_image = {
                "type": "numpy",
                "value": pickle.dumps(image_slice)
            }

            request = ObjectDetectionInferenceRequest(
                api_key=self._api_key,
                model_id=model_id,
                image=[inference_image],
                class_agnostic_nms=class_agnostic_nms,
                class_filter=class_filter,
                confidence=confidence,
                iou_threshold=iou_threshold,
                source="workflow-execution",
            )

            predictions = model.infer_from_request(request)[0]
            detections = sv.Detections.from_inference(predictions)
            return detections

        slicer = sv.InferenceSlicer(
            callback=slicer_callback,
            slice_wh=(slice_width, slice_height),
            overlap_ratio_wh=(overlap_ratio_width, overlap_ratio_height),
            iou_threshold=iou_threshold,
            thread_workers=1
        )

        predictions_batch = []
        for image in non_empty_inference_images:
            detections = slicer(image)
            xywh_bboxes = [xyxy_to_xywh(detection) for detection in detections.xyxy]
            predictions = [
                ObjectDetectionPrediction(
                    **{
                        "x": xywh_bboxes[i][0],
                        "y": xywh_bboxes[i][1],
                        "width": xywh_bboxes[i][2],
                        "height": xywh_bboxes[i][3],
                        "confidence": detections.confidence[i],
                        "class": detections["class_name"][i],
                        "class_id": int(detections.class_id[i]),
                    }
                )
                for i in range(len(detections)) if not class_filter
            ]

            response = ObjectDetectionInferenceResponse(
                predictions=predictions,
                image=InferenceResponseImage(
                    width=image.shape[1],
                    height=image.shape[0],
                ),
            )
            prediction = response.model_dump(by_alias=True, exclude_none=True)
            predictions_batch.append(prediction)
        
        results = self._post_process_result(
            images=non_empty_images,
            predictions=predictions_batch,
            class_filter=class_filter,
        )
        return images.align_batch_results(
            results=results,
            null_element={"predictions": None},
        )

    async def run_remotely(
        self,
        images: Batch[Optional[WorkflowImageData]],
        model_id: str,
        class_agnostic_nms: Optional[bool],
        class_filter: Optional[List[str]],
        confidence: Optional[float],
        iou_threshold: Optional[float],
        slice_width: Optional[int],
        slice_height: Optional[int],
        overlap_ratio_width: Optional[float],
        overlap_ratio_height: Optional[float],
    ) -> List[Dict[str, Union[sv.Detections, Any]]]:
        api_url = (
            LOCAL_INFERENCE_API_URL
            if WORKFLOWS_REMOTE_API_TARGET != "hosted"
            else HOSTED_CLASSIFICATION_URL
        )
        client = InferenceHTTPClient(
            api_url=api_url,
            api_key=self._api_key,
        )
        if WORKFLOWS_REMOTE_API_TARGET == "hosted":
            client.select_api_v0()
        client_config = InferenceConfiguration(
            class_agnostic_nms=class_agnostic_nms,
            class_filter=class_filter,
            confidence_threshold=confidence,
            max_batch_size=WORKFLOWS_REMOTE_EXECUTION_MAX_STEP_BATCH_SIZE,
            max_concurrent_requests=WORKFLOWS_REMOTE_EXECUTION_MAX_STEP_CONCURRENT_REQUESTS,
            source="workflow-execution",
        )
        client.configure(inference_configuration=client_config)
        non_empty_images = [i for i in images.iter_nonempty()]
        non_empty_inference_images = [i.numpy_image for i in non_empty_images]
        
        def slicer_callback(image_slice: np.ndarray):
            prediction = client.infer(
                inference_input=image_slice,
                model_id=model_id,
            )
            if isinstance(prediction, list):
                prediction = prediction[0]
            detections = sv.Detections.from_inference(prediction)
            return detections
        
        slicer = sv.InferenceSlicer(
            callback=slicer_callback,
            slice_wh=(slice_width, slice_height),
            overlap_ratio_wh=(overlap_ratio_width, overlap_ratio_height),
            iou_threshold=iou_threshold,
            thread_workers=1
        )

        predictions_batch = []
        for image in non_empty_inference_images:
            detections = slicer(image)
            xywh_bboxes = [xyxy_to_xywh(detection) for detection in detections.xyxy]
            predictions = [
                ObjectDetectionPrediction(
                    **{
                        "x": xywh_bboxes[i][0],
                        "y": xywh_bboxes[i][1],
                        "width": xywh_bboxes[i][2],
                        "height": xywh_bboxes[i][3],
                        "confidence": detections.confidence[i],
                        "class": detections["class_name"][i],
                        "class_id": int(detections.class_id[i]),
                    }
                )
                for i in range(len(detections)) if not class_filter
            ]

            response = ObjectDetectionInferenceResponse(
                predictions=predictions,
                image=InferenceResponseImage(
                    width=image.shape[1],
                    height=image.shape[0],
                ),
            )
            prediction = response.model_dump(by_alias=True, exclude_none=True)
            predictions_batch.append(prediction)
        
        results = self._post_process_result(
            images=non_empty_images,
            predictions=predictions_batch,
            class_filter=class_filter,
        )
        return images.align_batch_results(
            results=results, null_element={"predictions": None}
        )

    def _post_process_result(
        self,
        images: List[WorkflowImageData],
        predictions: List[dict],
        class_filter: Optional[List[str]],
    ) -> List[Dict[str, sv.Detections]]:
        predictions = convert_inference_detections_batch_to_sv_detections(predictions)
        predictions = attach_prediction_type_info_to_sv_detections_batch(
            predictions=predictions,
            prediction_type="object-detection",
        )
        predictions = filter_out_unwanted_classes_from_sv_detections_batch(
            predictions=predictions,
            classes_to_accept=class_filter,
        )
        predictions = attach_parents_coordinates_to_batch_of_sv_detections(
            images=images,
            predictions=predictions,
        )
        return [{"predictions": prediction} for prediction in predictions]

