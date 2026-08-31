#!/usr/bin/env python3
import unittest
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
spec = importlib.util.spec_from_file_location("nim_router_entry", os.path.join(os.path.dirname(__file__), "..", "nim-router.py"))
nim_router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nim_router)

ChatCompletionRequest = nim_router.ChatCompletionRequest
ModelRouter = nim_router.ModelRouter
HTTPException = nim_router.HTTPException


class TestVisionRouting(unittest.TestCase):
    def setUp(self):
        self.router = ModelRouter(api_key="test-key")
        self.router.models = self.router._load_fallback_models()
        self.router._healthy_pool = self.router._build_healthy_pool()

    def test_vision_model_identification(self):
        """Test keyword recognition for vision / multimodal models."""
        self.assertTrue(self.router._is_vision_model("meta/llama-3.2-11b-vision-instruct"))
        self.assertTrue(self.router._is_vision_model("meta/llama-3.2-90b-vision-instruct"))
        self.assertTrue(self.router._is_vision_model("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"))
        self.assertTrue(self.router._is_vision_model("qwen/qwen2-vl-72b-instruct"))
        self.assertTrue(self.router._is_vision_model("google/paligemma-3b-pt-224"))

        # Diffusion is banned and must NOT be considered a vision chat model
        self.assertFalse(self.router._is_vision_model("google/diffusiongemma-26b-a4b-it"))
        self.assertFalse(self.router._is_vision_model("stabilityai/stable-diffusion-3-medium"))

        self.assertFalse(self.router._is_vision_model("deepseek-ai/deepseek-v4-flash-0731"))
        self.assertFalse(self.router._is_vision_model("openai/gpt-oss-120b"))
        self.assertFalse(self.router._is_vision_model("minimaxai/minimax-m3"))
        self.assertFalse(self.router._is_vision_model("nvidia/riva-translate-4b-instruct-v2"))

    def test_banned_model_identification(self):
        """Verify non-chat, diffusion, calibration, and safety guard models are recognized as banned."""
        self.assertTrue(self.router._is_banned_model("google/diffusiongemma-26b-a4b-it"))
        self.assertTrue(self.router._is_banned_model("nvidia/ising-calibration-1.5-31b"))
        self.assertTrue(self.router._is_banned_model("nvidia/llama-3.1-nemoguard-8b-content-safety"))
        self.assertTrue(self.router._is_banned_model("nvidia/llama-3.1-nemotron-safety-guard-8b-v3"))
        self.assertTrue(self.router._is_banned_model("nvidia/nemotron-3.5-content-safety"))
        self.assertTrue(self.router._is_banned_model("nvidia/ai-synthetic-video-detector"))
        self.assertTrue(self.router._is_banned_model("nvidia/nemotron-parse"))
        self.assertTrue(self.router._is_banned_model("nvidia/nvclip"))
        self.assertTrue(self.router._is_banned_model("nvidia/embed-qa-4"))
        self.assertTrue(self.router._is_banned_model("nvidia/riva-translate-4b-instruct-v1.1"))

        # General chat and vision models must NOT be banned
        self.assertFalse(self.router._is_banned_model("openai/gpt-oss-120b"))
        self.assertFalse(self.router._is_banned_model("openai/gpt-oss-20b"))
        self.assertFalse(self.router._is_banned_model("nvidia/nemotron-3.5-lightning-30b-a3b"))
        self.assertFalse(self.router._is_banned_model("meta/llama-3.2-90b-vision-instruct"))
        self.assertFalse(self.router._is_banned_model("google/gemma-4-31b-it"))

    def test_banned_models_excluded_from_pool(self):
        """Verify banned models are completely excluded from active and healthy pools."""
        pool_ids = [m.get("id") for m in self.router.models]
        for mid in pool_ids:
            self.assertFalse(self.router._is_banned_model(mid), f"{mid} should be banned but found in pool")
        for mid in self.router._healthy_pool:
            self.assertFalse(self.router._is_banned_model(mid), f"{mid} should be banned but found in healthy pool")

    def test_text_only_request_detection(self):
        """Standard text messages should NOT be classified as vision requests."""
        req1 = ChatCompletionRequest(
            model="nim-free",
            messages=[{"role": "user", "content": "Hello, write a python function."}]
        )
        self.assertFalse(self.router._is_vision_request(req1))

        req2 = ChatCompletionRequest(
            model="nim-free",
            messages=[{"role": "user", "content": [{"type": "text", "text": "Just plain text"}]}]
        )
        self.assertFalse(self.router._is_vision_request(req2))

    def test_image_url_request_detection(self):
        """OpenAI-format image_url messages should be detected as vision requests."""
        req = ChatCompletionRequest(
            model="nim-free",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}}
                    ]
                }
            ]
        )
        self.assertTrue(self.router._is_vision_request(req))

    def test_base64_image_request_detection(self):
        """Base64 data URI image messages should be detected as vision requests."""
        req = ChatCompletionRequest(
            model="nim-free",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze diagram"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."}}
                    ]
                }
            ]
        )
        self.assertTrue(self.router._is_vision_request(req))

    def test_ollama_images_field_detection(self):
        """Messages with images array field should be detected as vision requests."""
        req = ChatCompletionRequest(
            model="nim-free",
            messages=[
                {
                    "role": "user",
                    "content": "Describe this",
                    "images": ["data:image/jpeg;base64,..."]
                }
            ]
        )
        self.assertTrue(self.router._is_vision_request(req))

    def test_candidate_pool_isolation_for_vision(self):
        """Verify that vision requests only select vision models in candidate pool."""
        req = ChatCompletionRequest(
            model="nim-free",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}}
                    ]
                }
            ]
        )
        is_vision = self.router._is_vision_request(req)
        self.assertTrue(is_vision)

        pool = [m.get("id") for m in self.router.models if m.get("id")]
        vision_candidates = [mid for mid in pool if self.router._is_vision_model(mid)]
        
        for mid in vision_candidates:
            self.assertTrue(self.router._is_vision_model(mid))
        self.assertNotIn("openai/gpt-oss-120b", vision_candidates)
        self.assertNotIn("deepseek-ai/deepseek-v4-flash-0731", vision_candidates)
        self.assertNotIn("google/diffusiongemma-26b-a4b-it", vision_candidates)

    def test_pool_auto_recovery_when_exhausted(self):
        """Verify that if all models are marked unhealthy, pool auto-recovers to prevent 500 error."""
        # Mark all models unhealthy
        for m in self.router.models:
            mid = m.get("id")
            self.router._health[mid] = {"failures": 5, "last_check": 9999999999, "healthy": False}
        
        # Build healthy pool should auto-reset and return available models
        recovered_pool = self.router._build_healthy_pool()
        self.assertGreater(len(recovered_pool), 0)
        self.assertIn("openai/gpt-oss-120b", recovered_pool)

    def test_rate_limit_penalization_and_cooldown(self):
        """Verify that 429 rate limit adds latency penalty and defers model in pool sorting."""
        model_a = "openai/gpt-oss-120b"
        model_b = "openai/gpt-oss-20b"
        self.router._latencies[model_a] = 0.2
        self.router._latencies[model_b] = 0.4

        # Model A gets 429
        self.router._record_failure(model_a, status_code=429)
        self.assertIn(model_a, self.router._rate_limited_until)

        # Healthy pool sort should now put model_b ahead of model_a
        pool = self.router._build_healthy_pool()
        idx_a = pool.index(model_a)
        idx_b = pool.index(model_b)
        self.assertLess(idx_b, idx_a)


if __name__ == "__main__":
    unittest.main()
