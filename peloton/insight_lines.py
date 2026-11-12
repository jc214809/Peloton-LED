"""Workout compare on the board: what the insight frames show for one insight. Standard library only.

`board_view(code, facts)` turns an insight's code and facts (peloton/workout_insights.py) into the content of the
card, bars and sentence frames (`display/ui/last_workout_screen.py` draws them). Every line is upper case and at most
LINE_MAX characters, the width of the `stats` font's 60 px (a fixed 4 px advance on both boards), so this module
wraps by character count and imports nothing. Only a movement name on the reason line may run longer: it scrolls.

`workout_insights`, `demo` and the dashboard import this module, so it must not import any of them back.
"""
LINE_MAX = 15
LINES_64 = 5               # sentence lines on the 64x64 card
LINES_32 = 3               # sentence lines on one 64x32 page
PAGES_32 = 2
MAX_BOARD_INSIGHTS = 2
MAX_BLOCKS = 30            # more counted sets than this are drawn as this many blocks, scaled
HIDDEN_CODES = ('too_few', 'nothing', 'freestyle', 'incomplete', 'unsupported', 'no_tracker')

GOLD = (255, 200, 0)
AMBER = (255, 140, 0)
GREEN = (60, 220, 110)
RED = (230, 40, 40)
SOFT_WHITE = (200, 205, 215)   # not 255: full white is glaring on the panel
COLOURS = {'output_down': AMBER, 'missed_targets': AMBER, 'resistance_low': AMBER, 'cadence_low': AMBER,
           'pace_low': AMBER, 'output_up': GREEN, 'go_up_lighter': GREEN, 'go_up_streak': GREEN,
           'went_heavier': GREEN, 'effort_low': GREEN, 'effort_high': RED, 'in_line': SOFT_WHITE}
OUTPUT_CODES = ('output_down', 'output_up', 'in_line')
CALLOUT_CODES = ('resistance_low', 'cadence_low', 'pace_low')
STRENGTH_CODES = ('go_up_lighter', 'went_heavier', 'go_up_streak', 'missed_targets')


def number(value, unit):
    """A value as printed everywhere: watts and pounds whole, mph to one decimal."""
    return f'{value:.1f}' if unit == 'mph' else f'{value:.0f}'


def wrap(text, width=LINE_MAX):
    """Words into lines of at most `width` characters; a longer word is cut across lines."""
    lines, current = [], ''
    for word in text.split():
        while len(word) > width:
            if current:
                lines.append(current)
                current = ''
            lines.append(word[:width])
            word = word[width:]
        trial = f'{current} {word}'.strip()
        if len(trial) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    return lines + [current] if current else lines


def _fitting(*sentences):
    """The first sentence that wraps to LINES_64 lines, else the last one (which always does)."""
    return next((sentence for sentence in sentences[:-1] if len(wrap(sentence)) <= LINES_64), sentences[-1])


def _plural(noun):
    return noun + ('es' if noun.endswith('s') else 's')


def _similar(facts):
    """What an output or effort insight was compared with, in at most LINE_MAX characters."""
    n, noun = facts['n'], _plural(facts['noun']).upper()
    if facts.get('real') is not None and facts['real'] < n:
        line = f'{n} CLOSEST {noun}'
    else:
        line = f'{n} SIMILAR {noun}'
    return line if len(line) <= LINE_MAX else f'VS {n} SIMILAR'


def _bars(today, usual, unit):
    return {'kind': 'bars', 'today': today, 'usual': usual, 'today_text': number(today, unit),
            'usual_text': number(usual, unit), 'unit': 'MPH' if unit == 'mph' else unit.upper()}


def _output(code, facts):
    unit = facts['unit'].lower()
    a, b = number(facts['value'], unit), number(facts['usual'], unit)
    u = 'MPH' if unit == 'mph' else 'W'
    reason = facts.get('reason')
    extra, why = '', None
    if code == 'output_down':
        headline = 'PACE DOWN' if facts['foot'] else 'OUTPUT DOWN'
        extra, why = {'easier': ('HR LOWER TOO: AN EASIER DAY.', 'AN EASIER DAY'),
                      'cost_more': ('HR NOT LOWER: LESS PER HEARTBEAT.', 'LESS PER BEAT')}.get(reason, ('', None))
        lead = headline
    elif code == 'output_up':
        headline = lead = f"STRONG {facts['noun'].upper()}"
        if reason == 'efficient':
            extra, why = 'MORE PER HEARTBEAT THAN USUAL.', 'MORE PER BEAT'
    elif facts.get('close'):
        headline = lead = 'ON YOUR USUAL'
        why = 'RIGHT IN LINE'
    else:
        headline, why = 'IN YOUR RANGE', 'IN YOUR RANGE'
        lead = 'IN YOUR USUAL RANGE'
    if code == 'in_line':
        sentence = f'{lead}: {a} {u} VS {b}.'
    else:
        sentence = _fitting(f'{lead}: {a} {u} VS YOUR USUAL {b}. {extra}'.strip(),
                            f'{lead}: {a} {u} VS USUAL {b}. {extra}'.strip(),
                            f'{lead}: {a} {u} VS USUAL {b}.')
    figure = _bars(facts['value'], facts['usual'], unit if unit == 'mph' else 'W')
    return headline, sentence, figure, why, _similar(facts)


def _effort(code, facts):
    word = 'HARDEST' if code == 'effort_high' else 'EASIEST'
    n = facts['n']
    sentence = f"{word} {facts['noun'].upper()} OF YOUR LAST {n} BY HEART RATE."
    figure = {'kind': 'bars', 'today': facts['rate'], 'usual': facts['usual_rate'],
              'today_text': f"{facts['rate']:.2f}", 'usual_text': f"{facts['usual_rate']:.2f}", 'unit': ''}
    # The bars are Strive per minute of class, which needs saying: the card and sentence say 'of your last n'.
    return f'{word} BY HR', sentence, figure, 'STRIVE PER MIN', _similar(facts)


def _callout(code, facts):
    pct = int(round(facts['pct']))
    headline, sentence, why = {
        'resistance_low': ('RESISTANCE LOW', f'RESISTANCE UNDER THE CALLOUT {pct}% OF THE WORK: TURN IT UP.',
                           'TURN IT UP'),
        'cadence_low': ('CADENCE LOW', f'CADENCE UNDER THE CALLOUT {pct}% OF THE WORK: PICK IT UP.', 'PICK IT UP'),
        'pace_low': ('UNDER PACE', f'UNDER THE PACE TARGET {pct}% OF THE TIME: PUSH, OR DROP A LEVEL.',
                     'PUSH THE PACE'),
    }[code]
    return headline, sentence, {'kind': 'share', 'pct': max(0, min(100, pct))}, why, 'VS THE CALLOUTS'


def _strength(code, facts):
    if code == 'go_up_streak':
        lb, n, cat = number(facts['lb'], 'lb'), facts['n'], facts['category'].upper()
        sentence = _fitting(f'GO UP FROM {lb}LB ON {cat}: {n} CLASSES IN A ROW OVER TARGET.',
                            f'GO UP FROM {lb}LB ON {cat}: {n} IN A ROW OVER TARGET.')
        return (f'GO UP: {cat}', sentence, {'kind': 'blocks', 'total': n, 'lit': n, 'label': 'IN A ROW'},
                f'FROM {lb}LB', 'VS PAST CLASSES')
    if code == 'missed_targets':
        missed, sets, name = facts['missed'], facts['sets'], facts['movement'].upper()
        sentence = _fitting(f'SHORT ON {missed} OF {sets} SETS, MOSTLY {name}: DROP A WEIGHT.',
                            f'SHORT ON {missed} OF {sets} SETS: DROP A WEIGHT.')
        total, lit = sets, missed
        if total > MAX_BLOCKS:
            total, lit = MAX_BLOCKS, round(missed * MAX_BLOCKS / sets)
        return ('DROP A WEIGHT', sentence, {'kind': 'blocks', 'total': total, 'lit': lit, 'label': ''},
                f'{missed} OF {sets} SHORT', 'VS PAST CLASSES')
    lb, usual = number(facts['lb'], 'lb'), number(facts['usual'], 'lb')
    on = facts['movement'].upper()
    if code == 'went_heavier' and not facts.get('on_movement', True):
        on = f"{facts['category'].upper()} WEIGHTS"
    if code == 'go_up_lighter':
        head = f'GO UP A WEIGHT ON {on}: {lb}LB'
        # A name too long even then leaves the sentence: the bars frame's reason line shows it.
        sentence = _fitting(f"{head} VS USUAL {usual}, REPS +{facts['pct']}%.", f'{head} VS USUAL {usual}.',
                            f'{head} (USUAL {usual}).', f'GO UP A WEIGHT: {lb}LB VS USUAL {usual}.')
        headline = 'GO UP A WEIGHT'
    else:
        head = f'HEAVIER ON {on}: {lb}LB'
        sentence = _fitting(f'{head} VS USUAL {usual}, EVERY TARGET HIT.', f'{head} VS USUAL {usual}.',
                            f'{head} (USUAL {usual}).', f'HEAVIER: {lb}LB VS USUAL {usual}. KEEP IT.')
        headline = 'HEAVIER: KEEP'
    return headline, sentence, _bars(facts['lb'], facts['usual'], 'lb'), on, 'VS PAST CLASSES'


def _rule(code):
    if code in OUTPUT_CODES:
        return _output
    if code in ('effort_high', 'effort_low'):
        return _effort
    if code in CALLOUT_CODES:
        return _callout
    if code in STRENGTH_CODES:
        return _strength
    return None


def board_view(code, facts):
    """What the insight frames show, or None for a hidden or unknown code or facts that lack a number.

    {'code', 'colour', 'headline', 'sentence', 'lines64', 'pages32', 'footer', 'figure', 'reason'}: `lines64` the
    sentence in at most LINES_64 lines, `pages32` in one or two pages of at most LINES_32, `reason` None when the
    bars frame has no line under the figure. `figure` is bars (today against the usual), a share bar or blocks.
    """
    rule = _rule(code)
    if code in HIDDEN_CODES or rule is None:
        return None
    try:
        headline, sentence, figure, reason, footer = rule(code, facts or {})
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    lines = wrap(sentence)
    lines64 = lines[:LINES_64]
    pages32 = [lines[i:i + LINES_32] for i in range(0, min(len(lines), LINES_32 * PAGES_32), LINES_32)]
    return {'code': code, 'colour': list(COLOURS[code]), 'headline': headline, 'sentence': sentence,
            'lines64': lines64, 'pages32': pages32, 'footer': footer, 'figure': figure, 'reason': reason}


def board_insights(messages, limit=MAX_BOARD_INSIGHTS):
    """The views of the first `limit` (code, text, facts) the board shows, in order."""
    views = []
    for code, _text, facts in messages:
        view = board_view(code, facts)
        if view:
            views.append(view)
            if len(views) == limit:
                break
    return views
