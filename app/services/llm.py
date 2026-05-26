import json
import time
from typing import Type, TypeVar
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError
from app.config import settings

T = TypeVar("T", bound=BaseModel)


class LLMService:
    def __init__(self):
        self._client = None
        self.model = settings.LLM_MODEL
        self.max_retries = 3

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
            )
        return self._client

    def call_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_model: Type[T],
        temperature: float = 0.3,
    ) -> tuple[T | None, list[str]]:
        errors = []
        schema_json = json.dumps(
            self._clean_schema(schema_model.model_json_schema()),
            ensure_ascii=False,
        )

        full_system = (
            f"{system_prompt}\n\n"
            f"CRITICAL: You MUST output ONLY valid JSON matching this schema:\n"
            f"```json\n{schema_json}\n```\n"
            "Do NOT include any text before or after the JSON."
        )

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user_prompt},
        ]

        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=4096,
                    extra_body={
                        "thinking": {"type": "enabled"},
                        "reasoning_effort": "high",
                    },
                )

                raw = response.choices[0].message.content
                if not raw:
                    raise ValueError("Empty response from LLM")

                json_str = raw.strip()
                if json_str.startswith("```"):
                    lines = json_str.split("\n")
                    json_str = "\n".join(lines[1:-1]).strip()

                json_data = json.loads(json_str)
                parsed = schema_model.model_validate(json_data)
                return parsed, []

            except (ValidationError, json.JSONDecodeError, ValueError, OpenAIError) as e:
                error_msg = f"Attempt {attempt + 1}/{self.max_retries}: {e}"
                errors.append(error_msg)

                if attempt < self.max_retries - 1:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Previous output was invalid: {e}\n"
                                "Please fix the JSON to match the schema exactly and retry."
                            ),
                        }
                    )
                    time.sleep(2**attempt)
                else:
                    return None, errors

        return None, errors

    def call_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict],
        temperature: float = 0.3,
    ) -> list[dict]:
        """Ask LLM to return tool calls as a JSON array. Works across providers."""
        tool_descriptions = []
        for t in tools:
            fn = t["function"]
            params = json.dumps(fn["parameters"], ensure_ascii=False)
            tool_descriptions.append(f"  - {fn['name']}: {fn['description']}\n    Parameters: {params}")

        full_system = (
            f"{system_prompt}\n\n"
            "AVAILABLE TOOLS:\n"
            f"{chr(10).join(tool_descriptions)}\n\n"
            "INSTRUCTIONS: Return ONLY a JSON array of tool calls. Each call is:\n"
            '  {"id": "call_1", "name": "tool_name", "arguments": {...}}\n'
            "CRITICAL: Use the 'id' from add_node calls as source_id/target_id in add_edge.\n"
            'Example: add_node with id="n1" → add_edge with source_id="n1" and target_id="n2".\n'
            "Create ALL nodes first, then ALL edges. Aim for 8-15 nodes with connecting edges."
        )

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=8192,
                temperature=temperature,
                extra_body={
                    "thinking": {"type": "enabled"},
                    "reasoning_effort": "high",
                },
            )
            raw = response.choices[0].message.content or ""
            json_str = raw.strip()
            # Remove markdown fences
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
            json_str = json_str.strip()
            # Try to find the outermost JSON array
            if "[" in json_str:
                start = json_str.index("[")
                end = json_str.rindex("]") + 1
                json_str = json_str[start:end]
            return json.loads(json_str)
        except Exception as e:
            return [{"id": "error", "name": "error", "arguments": {"message": str(e)}}]

    def call_simple(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
    ) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2048,
                temperature=temperature,
                extra_body={
                    "thinking": {"type": "enabled"},
                    "reasoning_effort": "high",
                },
            )
            return response.choices[0].message.content or ""
        except OpenAIError as e:
            return f"LLM Error: {e}"

    @staticmethod
    def _clean_schema(schema: dict) -> dict:
        clean = schema.copy()
        for key in ("$defs", "title", "additionalProperties"):
            clean.pop(key, None)
        if "properties" in clean:
            for prop in clean["properties"].values():
                if isinstance(prop, dict):
                    prop.pop("title", None)
        return clean
