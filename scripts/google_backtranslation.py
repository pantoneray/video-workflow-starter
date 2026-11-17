"""Google Cloud Translation Basic blind backtranslation; no Gemini fallback.

Only the target-language text is transmitted. Unknown request outcomes are not
retried; the existing model-stage cache requires explicit reconciliation first.
"""
import html
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = 'https://translation.googleapis.com/language/translate/v2'


def preflight(config):
    if config.get('backtranslation_provider', 'google_translate') != 'google_translate':
        raise ValueError('盲回译须使用 google_translate；Gemini 仅做独立校对')
    if config.get('backtranslation_model', 'nmt') != 'nmt':
        raise ValueError('请将 backtranslation_model 改为 nmt；旧 Gemini 回译配置不再执行')
    if not os.environ.get('GOOGLE_TRANSLATE_API_KEY'):
        raise ValueError('未配置 GOOGLE_TRANSLATE_API_KEY；盲回译未完成，不回退 Gemini')


def translate_json(payload, model, *, opener=None, sleep=time.sleep):
    """Provider for model_stage; payload contains q only, never Chinese source."""
    preflight({'backtranslation_model': model})
    data = json.loads(payload)
    if set(data) != {'q'} or not isinstance(data['q'], str) or not data['q'].strip():
        raise ValueError('盲回译请求仅允许非空目标语文本 q')
    key = os.environ['GOOGLE_TRANSLATE_API_KEY']
    # API key is passed only to the official endpoint; never emit request URLs.
    url = ENDPOINT + '?' + urllib.parse.urlencode({'key': key})
    body = json.dumps({'q': data['q'], 'target': 'zh-CN', 'format': 'text', 'model': 'nmt'}).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    open_request = opener or urllib.request.urlopen
    for attempt in range(3):
        try:
            with open_request(request, timeout=30) as response:
                result = json.load(response)
            rows = result.get('data', {}).get('translations', [])
            if len(rows) != 1 or not isinstance(rows[0].get('translatedText'), str) or not rows[0]['translatedText'].strip():
                raise ValueError('invalid_google_translate_response')
            return {'text': html.unescape(rows[0]['translatedText']), 'provider': 'google_translate',
                    'model': 'nmt', 'detected_source_language': rows[0].get('detectedSourceLanguage'),
                    'usage': {'input_characters': len(data['q']), 'requests_attempted': attempt + 1,
                              'provider_billed_characters': None, 'input_tokens': None, 'output_tokens': None}}
        except urllib.error.HTTPError as exc:
            # Only explicit quota/rate rejection is automatically retryable.
            if exc.code == 429 and attempt < 2:
                sleep(2 ** attempt)
                continue
            raise RuntimeError('google_translate_http_' + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError('google_translate_outcome_unknown_check_before_retry') from None
        except (ValueError, KeyError, TypeError):
            raise RuntimeError('google_translate_response_invalid_check_before_retry') from None


def backtranslate(target, language, *, workdir=None, retry_unknown=False):
    from translation_review import model_stage, sha
    preflight({})
    payload = json.dumps({'q': target}, ensure_ascii=False)
    result = (model_stage('backtranslation', payload, 'google-translate-nmt', workdir,
                         provider=lambda p, m: translate_json(p, 'nmt'), retry_unknown=retry_unknown)
              if workdir else translate_json(payload, 'nmt'))
    return {**result, 'target_language': language, 'target_sha256': sha(target)}
