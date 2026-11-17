"""Plan caption styling from sampled video; explicit template choices stay explicit."""
import json
from pathlib import Path
from caption_contrast import recommend
from caption_options import configure


def plan(video, vendor, *, template='auto', spec=None, shift_up=80, highlight=None,
         course=None, contrast=None, ffmpeg='ffmpeg'):
    if template not in ('auto', 'B', 'C', 'D', 'E', 'F'):
        raise ValueError('Choose auto or a full-bleed portrait template')
    if contrast not in (None, 'outline', 'box', 'template'):
        raise ValueError('contrast must be outline, box or template')
    explicit = spec is not None or template != 'auto'
    def read(name):
        path = Path(spec).resolve(strict=True) if spec else next((Path(vendor) / 'specs').glob(name + '_*.json'))
        value = json.loads(path.read_text(encoding='utf-8'))
        if value['layout']['mode'] == 'threeband':
            raise ValueError('Choose a full-bleed portrait template')
        return value
    initial = read('B' if template == 'auto' else template)
    # Assess the actual configured caption position before selecting a style.
    y = configure(initial, shift_up)['captions']['y_center']
    report = recommend(video, y=y, ffmpeg=ffmpeg)
    selected = initial
    if not explicit:
        for candidate in report['recommended_templates']:
            option = read(candidate)
            if highlight and 'highlight' not in option['captions']:
                continue
            selected = option
            break
        else:
            raise ValueError('No recommended template supports requested highlight')
        actual_y = configure(selected, shift_up)['captions']['y_center']
        if actual_y != y:
            raise ValueError('Recommended template changes caption band; explicit review required')
    # Explicit template/spec retains its styling unless contrast was requested.
    applied = (report['contrast'] if not explicit and contrast is None else contrast)
    if applied == 'template':
        applied = None
    settings = configure(selected, shift_up, highlight, course, applied)
    report.update(requested_template=template, selected_template=settings['id'],
                  selection='explicit_preserved' if explicit else 'automatic_sample_recommendation',
                  applied_contrast=applied, requested_contrast=contrast,
                  explicit_style_differs_from_suggestion=explicit and applied != report['contrast'])
    return settings, report
