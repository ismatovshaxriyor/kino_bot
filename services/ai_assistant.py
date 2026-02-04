""""Kino Bot uchun AI Assistant moduli - V3.1 FIXED
✅ Internet qidiruv
✅ Rate limiting (API limit muammosini hal qilish)
✅ Response caching
✅ Auto-retry
✅ Token Limit Fix (Uzuq gaplar muammosi hal qilindi)
"""

from google import genai
from google.genai import types
from typing import Optional
import logging
import requests
import json
import time
from functools import wraps
import hashlib
import os

try:
    from utils.settings import GEMINI_API_KEY, GEMINI_MODEL
except ImportError:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = "gemini-2.5-flash"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

def retry_on_quota_error(max_retries=3, wait_time=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        wait = wait_time * (2 ** attempt)
                        logger.info(f"⏰ {wait} soniya kutilmoqda...")
                        time.sleep(wait)

                    return func(*args, **kwargs)

                except Exception as e:
                    error_msg = str(e)

                    if "429" in error_msg or "quota" in error_msg.lower() or "resource" in error_msg.lower():
                        logger.warning(f"🚫 API limit! Urinish {attempt + 1}/{max_retries}")

                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                            continue
                        else:
                            return "⚠️ Kechirasiz, hozir serverlarimiz band. Iltimos, 1-2 daqiqadan so'ng qayta urinib ko'ring."
                    else:
                        logger.error(f"Kutilmagan xatolik: {e}")
                        return f"❌ Tizim xatoligi yuz berdi: {str(e)}"
            return "❌ Noma'lum xatolik."
        return wrapper
    return decorator


class WebSearchHelper:
    @staticmethod
    def search_movie_info(query: str) -> str:
        try:
            url = "https://api.duckduckgo.com/"
            params = {
                'q': query,
                'format': 'json',
                'no_html': 1,
                'skip_disambig': 1
            }

            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                try:
                    data = response.json()
                    result = []

                    if data.get('Abstract'):
                        result.append(f"📝 {data['Abstract']}")

                    if data.get('RelatedTopics'):
                        for topic in data['RelatedTopics'][:3]:
                            if isinstance(topic, dict) and topic.get('Text'):
                                result.append(f"• {topic['Text']}")

                    if result:
                        return "\n\n".join(result)
                except json.JSONDecodeError:
                    return ""

            return ""

        except Exception as e:
            logger.error(f"Web qidiruv xatoligi: {e}")
            return ""


class MovieAIAssistant:
    def __init__(self, api_key: str):
        self.api_key = api_key
        if not self.api_key:
            logger.error("API Key topilmadi!")

        self.client = genai.Client(api_key=self.api_key)
        self.model = GEMINI_MODEL

        self._generation_config = types.GenerateContentConfig(
            temperature=0.7
        )

        self.web_search = WebSearchHelper()

        self._cache = {}
        self._cache_timeout = 900

        # Rate limiting
        self._last_request_time = 0
        self._min_request_interval = 2.0

        self.system_instruction = """
Sen "KinoBot" uchun professional va do'stona AI maslahatchisan.

SENING VAZIFANG:
Foydalanuvchiga kino, serial va multfilmlar bo'yicha eng yaxshi maslahatlarni berish.

JAVOB QAYTARISH QOIDALARI:
1. Javobing doimo TO'LIQ va TUGALLANGAN bo'lishi shart. Gapni yarmida tashlab ketma.
2. Ro'yxat sanayotganda, har bir kino haqida qisqacha (1-2 gap) ma'lumot ber.
3. Samimiy va o'zbek tilida ravon gapir.
4. "Salom" deb boshlash shart emas, to'g'ridan-to'g'ri va aniq javob ber (agar salom berilmasa).
5. Agar internet ma'lumoti berilsa, undan foydalan, lekin "internetdan oldim" dema.

AGAR KINO TAVSIYA QILSANG:
- Kino nomi (Chiqish yili)
- Qisqacha syujet
- Nega buni ko'rish kerak?

Faqat kino mavzusida gaplash. Boshqa mavzularga xushmuomalalik bilan rad javobini ber. Xabarlaringni stikerlar bilan boyit.
"""

    def _wait_for_rate_limit(self):
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self._min_request_interval:
            wait_time = self._min_request_interval - time_since_last
            time.sleep(wait_time)

        self._last_request_time = time.time()

    def _get_cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def _check_cache(self, cache_key: str) -> Optional[str]:
        if cache_key in self._cache:
            cached_time, cached_response = self._cache[cache_key]
            if time.time() - cached_time < self._cache_timeout:
                logger.info("📦 Cache dan javob olindi")
                return cached_response
        return None

    def _save_cache(self, cache_key: str, response: str):
        self._cache[cache_key] = (time.time(), response)
        if len(self._cache) > 200:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]

    @retry_on_quota_error(max_retries=3, wait_time=3)
    def get_movie_recommendation(self, user_query: str, user_history: Optional[list] = None) -> str:

        cache_key = self._get_cache_key(f"rec_{user_query}")
        cached = self._check_cache(cache_key)
        if cached: return cached

        web_info = self.web_search.search_movie_info(user_query)

        context_part = f"\nQO'SHIMCHA MA'LUMOT: {web_info}" if web_info else ""

        full_prompt = f"""
{self.system_instruction}

{context_part}

FOYDALANUVCHI SAVOLI: "{user_query}"

Iltimos, yuqoridagi savolga batafsil va tugallangan javob ber:
"""

        self._wait_for_rate_limit()

        response = self.client.models.generate_content(
            model=self.model,
            contents=full_prompt,
            config=self._generation_config,
        )

        if not response.text:
            return "Kechirasiz, javobni shakllantirishda xatolik bo'ldi."

        result = response.text
        self._save_cache(cache_key, result)

        logger.info(f"✅ AI javob berdi: {len(result)} belgi")
        return result

    @retry_on_quota_error(max_retries=3, wait_time=3)
    def search_movie_info(self, movie_name: str) -> str:

        cache_key = self._get_cache_key(f"movie_{movie_name}")
        cached = self._check_cache(cache_key)
        if cached: return cached

        web_info = self.web_search.search_movie_info(f"{movie_name} movie")
        context_part = f"\nMA'LUMOT: {web_info}" if web_info else ""

        prompt = f"""
{self.system_instruction}

"{movie_name}" filmi haqida ma'lumot kerak.
{context_part}

Quyidagi strukturada javob ber:
1. 🎬 To'liq nomi va yili
2. 🎭 Janr va Rejissyor
3. 📝 Qisqacha tavsif (Spoiler yo'q)
4. 🌟 IMDB reytingi (taxminiy)
5. 💡 O'xshash 3 ta kino

Javobing to'liq bo'lsin.
"""

        self._wait_for_rate_limit()

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._generation_config,
        )

        result = response.text
        self._save_cache(cache_key, result)
        return result

    @retry_on_quota_error(max_retries=3, wait_time=3)
    def get_recommendations_by_genre(self, genre: str, count: int = 5) -> str:

        cache_key = self._get_cache_key(f"genre_{genre}_{count}")
        cached = self._check_cache(cache_key)
        if cached: return cached

        prompt = f"""
{self.system_instruction}

Menga "{genre}" janridagi eng zo'r {count} ta kinoni tavsiya qil.
Yangi (2020-2025) kinolarni ham qo'shishga harakat qil.

Har bir kino uchun:
1. Nomi (Yili)
2. Nega ko'rish kerak? (1 gap)

Ro'yxatni to'liq tugat.
"""

        self._wait_for_rate_limit()

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._generation_config,
        )

        result = response.text
        self._save_cache(cache_key, result)
        return result

ai_assistant = MovieAIAssistant(GEMINI_API_KEY)
