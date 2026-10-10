from .schemas import StoryboardSchema
from .scheduler import BASE_DURATIONS

SCRIPTS = (
    "Make room for something better.",
    "Meet the product made for your everyday life.",
    "Thoughtful details bring comfort and confidence to every moment.",
    "Choose Visora for your next move.",
)


def local_storyboard() -> StoryboardSchema:
    """Deterministic fixture; this module does not instantiate any AI SDK."""
    return StoryboardSchema.model_validate({
        "concept_title": "Offline pipeline acceptance",
        "product_metadata": {"name": "Mock product", "selling_points": ["Offline"],
                             "isolated_image_url": "mock://product"},
        "scenes": [{"scene_index": i + 1, "shot_type": "static placeholder",
                    "camera_motion": "none", "lighting_style": "flat",
                    "keyframe_prompt": f"Scene {i + 1}", "motion_prompt": "static",
                    "voiceover_script": script, "subtitle_text": script,
                    "planned_duration": BASE_DURATIONS[i]} for i, script in enumerate(SCRIPTS)]})
