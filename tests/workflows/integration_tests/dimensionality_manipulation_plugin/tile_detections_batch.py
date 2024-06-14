"""
This is just example, test implementation, please do not assume it being fully functional.
"""

from copy import deepcopy
from typing import List, Literal, Optional, Type, Union

import numpy as np
import supervision as sv
from pydantic import ConfigDict, Field

from inference.core.workflows.entities.base import (
    Batch,
    OutputDefinition,
    WorkflowImageData,
)
from inference.core.workflows.entities.types import (
    BATCH_OF_IMAGES_KIND,
    BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
    BATCH_OF_KEYPOINT_DETECTION_PREDICTION_KIND,
    BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND,
    StepOutputImageSelector,
    StepOutputSelector,
    WorkflowImageSelector,
)
from inference.core.workflows.prototypes.block import (
    BlockResult,
    WorkflowBlock,
    WorkflowBlockManifest,
)


class BlockManifest(WorkflowBlockManifest):
    model_config = ConfigDict(
        json_schema_extra={
            "short_description": "",
            "long_description": "",
            "license": "Apache-2.0",
            "block_type": "transformation",
        }
    )
    type: Literal["TileDetectionsBatch"]
    images_crops: Union[WorkflowImageSelector, StepOutputImageSelector] = Field(
        description="Reference an image to be used as input for step processing",
        examples=["$inputs.image", "$steps.cropping.crops"],
    )
    crops_predictions: StepOutputSelector(
        kind=[
            BATCH_OF_OBJECT_DETECTION_PREDICTION_KIND,
            BATCH_OF_INSTANCE_SEGMENTATION_PREDICTION_KIND,
            BATCH_OF_KEYPOINT_DETECTION_PREDICTION_KIND,
        ]
    ) = Field(
        description="Reference to predictions of detection-like model, that can be based of cropping "
        "(detection must define RoI - eg: bounding box)",
        examples=["$steps.my_object_detection_model.predictions"],
    )

    @classmethod
    def describe_outputs(cls) -> List[OutputDefinition]:
        return [
            OutputDefinition(name="visualisations", kind=[BATCH_OF_IMAGES_KIND]),
        ]


class TileDetectionsBatchBlock(WorkflowBlock):

    @classmethod
    def get_manifest(cls) -> Type[WorkflowBlockManifest]:
        return BlockManifest

    @classmethod
    def get_impact_on_data_dimensionality(
        cls,
    ) -> Literal["decreases", "keeps_the_same", "increases"]:
        return "decreases"

    @classmethod
    def accepts_batch_input(cls) -> bool:
        return True

    async def run(
        self,
        images_crops: Batch[Batch[WorkflowImageData]],
        crops_predictions: Batch[Batch[sv.Detections]],
    ) -> BlockResult:
        annotator = sv.BoundingBoxAnnotator()
        visualisations = []
        for image_crops, crop_predictions in zip(images_crops, crops_predictions):
            visualisations_batch_element = []
            for image, prediction in zip(image_crops, crop_predictions):
                annotated_image = annotator.annotate(
                    image.numpy_image.copy(),
                    prediction,
                )
                visualisations_batch_element.append(annotated_image)
            tile = sv.create_tiles(visualisations_batch_element)
            visualisations.append({"visualisations": tile})
        return visualisations
