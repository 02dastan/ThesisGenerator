import json
import asyncio
import re
from typing import Dict, List, Optional
from app.config_manager import load_api_keys, load_settings, load_system_prompt
from app.file_storage import log_error

FALLBACK_TOPICS = [
    {
        "title": "Ошибка генерации — попробуйте позже",
        "relevance": "Сервис временно недоступен. Администратор уже работает над устранением проблемы.",
        "novelty": "—",
        "structure": ["Введение", "Основная часть", "Заключение"],
        "methods": "—",
        "expected_result": "—",
        "required_resources": "—",
        "difficulty": "easy",
        "pages_approx": 60,
    }
]


def _clean_json(text: str) -> str:
    """Strip markdown wrappers and extract JSON."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    return text


def _parse_topics(content: str, max_count: int) -> List[Dict]:
    content = _clean_json(content)
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data[:max_count]
        if isinstance(data, dict) and "topics" in data:
            return data["topics"][:max_count]
    except json.JSONDecodeError:
        # Try to extract JSON array from the text
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())[:max_count]
            except Exception:
                pass
    return FALLBACK_TOPICS


def _build_user_prompt(student_data: Dict, settings: Dict, regenerate: bool = False) -> str:
    max_topics = settings.get("max_topics_per_request", 5)
    regen_note = "\n\nВАЖНО: Студент уже видел предыдущие варианты. Сгенерируй ПОЛНОСТЬЮ НОВЫЕ, непохожие темы." if regenerate else ""

    return f"""Студент специальности: {student_data.get('specialty', 'не указано')}
Интересы и ключевые слова: {student_data.get('interests', 'не указано')}
Доступные ресурсы: {student_data.get('resources', 'не указано')}
Срок до защиты: {student_data.get('deadline', 'не указано')}
Тип работы: {student_data.get('work_type', 'не указано')}
Уровень (бакалавр/магистр): {student_data.get('level', 'бакалавр')}
Использовать AI в работе: {student_data.get('use_ai', 'нет')}{regen_note}

Сгенерируй ровно {max_topics} уникальных, оригинальных и выполнимых тем для дипломной работы.
Верни ТОЛЬКО JSON-массив из {max_topics} объектов. Каждый объект должен содержать поля:
- title (string): название темы
- relevance (string): актуальность (2-3 предложения)
- novelty (string): научная/прикладная новизна
- structure (array of strings): список глав (4-6 глав)
- methods (string): методы исследования
- expected_result (string): ожидаемый результат
- required_resources (string): необходимые ресурсы и ПО
- difficulty (string): "easy", "medium" или "hard"
- pages_approx (number): примерный объём страниц

Ответ должен быть ТОЛЬКО валидным JSON-массивом, без пояснений."""


class AIEngine:
    def __init__(self):
        self._reload()

    def _reload(self):
        self.settings = load_settings()
        self.keys = load_api_keys()
        self.system_prompt = load_system_prompt()

    def get_available_provider(self) -> Optional[str]:
        self._reload()
        for p in self.settings.get("provider_order", ["openai", "anthropic", "google", "mistral"]):
            info = self.keys.get(p, {})
            if info.get("enabled") and info.get("key"):
                return p
        return None

    async def generate_topics(self, student_data: Dict, regenerate: bool = False) -> List[Dict]:
        self._reload()
        provider_order = self.settings.get("provider_order", ["openai", "anthropic", "google", "mistral"])
        user_prompt = _build_user_prompt(student_data, self.settings, regenerate)
        last_error = None

        for p in provider_order:
            info = self.keys.get(p, {})
            if not info.get("enabled") or not info.get("key"):
                continue
            try:
                topics = await self._call_provider(p, info["key"], user_prompt)
                return topics
            except Exception as e:
                last_error = str(e)
                log_error(p, last_error)
                continue

        if last_error:
            raise Exception(f"Все провайдеры недоступны. Последняя ошибка: {last_error}")
        raise Exception("Нет доступных API-ключей. Зайдите в админ-панель и добавьте ключи.")

    async def _call_provider(self, provider: str, api_key: str, user_prompt: str) -> List[Dict]:
        timeout = self.settings.get("timeout_seconds", 30)
        max_topics = self.settings.get("max_topics_per_request", 5)
        temperature = self.settings.get("temperature", 0.7)

        if provider == "openai":
            return await self._call_openai(api_key, user_prompt, timeout, temperature, max_topics)
        elif provider == "anthropic":
            return await self._call_anthropic(api_key, user_prompt, timeout, temperature, max_topics)
        elif provider == "google":
            return await self._call_google(api_key, user_prompt, timeout, temperature, max_topics)
        elif provider == "mistral":
            return await self._call_mistral(api_key, user_prompt, timeout, temperature, max_topics)
        else:
            raise Exception(f"Провайдер {provider} не поддерживается")

    async def _call_openai(self, api_key: str, user_prompt: str, timeout: int,
                           temperature: float, max_topics: int) -> List[Dict]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        model = self.settings.get("default_model", "gpt-4-turbo")
        # Use a GPT model if default is not a GPT model
        if not model.startswith("gpt"):
            model = "gpt-4-turbo"
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        content = response.choices[0].message.content
        return _parse_topics(content, max_topics)

    async def _call_anthropic(self, api_key: str, user_prompt: str, timeout: int,
                               temperature: float, max_topics: int) -> List[Dict]:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)
        model = self.settings.get("default_model", "claude-3-opus-20240229")
        if not model.startswith("claude"):
            model = "claude-3-haiku-20240307"
        message = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )
        content = message.content[0].text
        return _parse_topics(content, max_topics)

    async def _call_google(self, api_key: str, user_prompt: str, timeout: int,
                           temperature: float, max_topics: int) -> List[Dict]:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model_name = "gemini-1.5-flash"
        model = genai.GenerativeModel(
            model_name,
            system_instruction=self.system_prompt,
        )
        full_prompt = user_prompt
        response = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: model.generate_content(
                    full_prompt,
                    generation_config=genai.types.GenerationConfig(temperature=temperature),
                ),
            ),
            timeout=timeout,
        )
        content = response.text
        return _parse_topics(content, max_topics)

    async def _call_mistral(self, api_key: str, user_prompt: str, timeout: int,
                             temperature: float, max_topics: int) -> List[Dict]:
        from mistralai.client import MistralClient
        from mistralai.models.chat_completion import ChatMessage
        client = MistralClient(api_key=api_key)
        model = "mistral-large-latest"
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        response = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.chat(model=model, messages=messages, temperature=temperature),
            ),
            timeout=timeout,
        )
        content = response.choices[0].message.content
        return _parse_topics(content, max_topics)

    async def verify_key(self, provider: str, api_key: str) -> Dict:
        """Test if an API key works. Returns {"ok": bool, "message": str}."""
        try:
            if provider == "openai":
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=api_key, timeout=10)
                models = await client.models.list()
                return {"ok": True, "message": f"Ключ рабочий. Доступно {len(list(models))} моделей."}

            elif provider == "anthropic":
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=api_key, timeout=10)
                msg = await client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "ping"}],
                )
                return {"ok": True, "message": "Ключ рабочий. Claude отвечает."}

            elif provider == "google":
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                models = list(genai.list_models())
                return {"ok": True, "message": f"Ключ рабочий. Доступно {len(models)} моделей Gemini."}

            elif provider == "mistral":
                from mistralai.client import MistralClient
                client = MistralClient(api_key=api_key)
                models = client.list_models()
                return {"ok": True, "message": "Ключ рабочий. Mistral отвечает."}

            else:
                return {"ok": False, "message": f"Провайдер {provider} не поддерживается"}

        except Exception as e:
            return {"ok": False, "message": f"Ошибка: {str(e)[:200]}"}
