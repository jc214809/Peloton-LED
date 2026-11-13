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
# The words standing in for "usual" (swap them here). IN_LINE_WORD heads and leads an insight within the
# usual range; TYPICAL_WORD names the usual figure (the median of the similar workouts) in sentences. The bars frame's
# label is display/ui/last_workout_screen.py's TYPICAL_LABEL.
IN_LINE_WORD = 'CONSISTENT'
TYPICAL_WORD = 'TYPICAL'
HIDDEN_CODES = ('too_few', 'nothing', 'freestyle', 'incomplete', 'unsupported', 'no_tracker')

GOLD = (255, 200, 0)
AMBER = (255, 140, 0)
GREEN = (60, 220, 110)
RED = (230, 40, 40)
SOFT_WHITE = (200, 205, 215)   # not 255: full white is glaring on the panel
COLOURS = {'output_down': AMBER, 'missed_targets': AMBER, 'resistance_low': AMBER, 'cadence_low': AMBER,
           'pace_low': AMBER, 'output_up': GREEN, 'go_up_lighter': GREEN, 'go_up_streak': GREEN,
           'went_heavier': GREEN, 'tough_class': GREEN, 'effort_low': GREEN, 'effort_high': RED, 'in_line': SOFT_WHITE}
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


# The strong workout's line when it got more out of each heartbeat than typical (reason 'efficient'): "same
# heart" only when the heart rate was within workout_insights.SAME_HR_BPM of typical, else what went up per beat.
SAME_HEART_LINE = 'SAME HEART, MORE {gain}.'
PER_BEAT_LINE = 'MORE {measure} PER HEARTBEAT.'


def _figures(a, b, unit, space=' '):
    """Today against the typical on a line of their own, each with its unit, else the unit once."""
    both = f'{a}{space}{unit} VS {b}{space}{unit}'
    return both if len(both) <= LINE_MAX else f'{a} VS {b}{space}{unit}'


def _parts(*choices):
    """The first tuple of parts (each starts a line) that wraps to LINES_64 lines, else the last."""
    def lines(parts):
        return sum(len(wrap(part)) for part in parts if part)
    chosen = next((c for c in choices[:-1] if lines(c) <= LINES_64), choices[-1])
    return tuple(part for part in chosen if part)


def _output(code, facts):
    unit = facts['unit'].lower()
    a, b = number(facts['value'], unit), number(facts['usual'], unit)
    u = 'MPH' if unit == 'mph' else 'W'
    figures = _figures(a, b, u)
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
            foot = unit == 'mph'
            if facts.get('same_hr'):
                extra, why = SAME_HEART_LINE.format(gain='SPEED' if foot else 'POWER'), 'SAME HEART'
            else:
                measure = 'SPEED' if foot else 'WATTS'
                extra, why = PER_BEAT_LINE.format(measure=measure), f'{measure} PER BEAT'
    elif facts.get('close'):
        headline = lead = IN_LINE_WORD
        why = 'RIGHT IN LINE'
    else:
        # The headline already says "in your range", so the bars frame's line says by how much.
        headline, lead = 'IN YOUR RANGE', f'IN YOUR {TYPICAL_WORD} RANGE'
        gap = facts['value'] - facts['usual']
        why = f"{number(abs(gap), unit)} {u} {'UNDER' if gap < 0 else 'OVER'}" if number(gap, unit).strip('-0.') \
            else 'RIGHT IN LINE'
    if code == 'in_line':
        sentence = (lead, figures)
    else:
        # The figures on a line of their own, as the in-line insight has them.
        sentence = _parts((f'{lead} VS YOUR {TYPICAL_WORD}', figures, extra),
                          (f'{lead} VS {TYPICAL_WORD}', figures, extra),
                          (lead, figures, extra), (lead, figures))
    figure = _bars(facts['value'], facts['usual'], unit if unit == 'mph' else 'W')
    return headline, sentence, figure, why, _similar(facts)


# The tough-class cheer (Joel's mock-up): its first 64x64 line runs the full 16 characters, edge to edge. The 64x32
# words page is the same cheer without the numbers (they are on the bars). ARROW in `reason_parts` is drawn in
# pixels by the screen, since the font has none.
CHEER_64 = ['WAY TO CHALLENGE', 'YOURSELF!', 'YOU TOOK ON A']
CHEER_32 = ['WAY TO', 'CHALLENGE', 'YOURSELF!']
ARROW = 'arrow'


def _tough(code, facts):
    unit = facts['unit'].lower()
    mine, usual = f"{facts['difficulty']:.1f}", f"{facts['usual_difficulty']:.1f}"
    ratings = wrap(f'{mine} CLASS, YOUR TYPICAL IS {usual}.')
    if len(ratings) > 2:  # a 10.0 class: '10.0 CLASS, YOUR' would run past the line
        ratings = wrap(f'{mine} CLASS. TYPICAL {usual}.')
    lines = CHEER_64 + ratings
    figure = _bars(facts['value'], facts['usual'], unit if unit == 'mph' else 'W')
    # `text` is the bottom line as words (for logs); `parts` is how the screen draws it, the arrow between.
    # A 10.0 class draws `10` on the bottom line: `10.0 → USUALLY 9.0` would be 67 px of the 63 it has.
    short = mine if len(mine) <= 3 else f"{facts['difficulty']:.0f}"
    reason = {'text': f'{mine} TO USUALLY {usual}', 'parts': [short, ARROW, f'USUALLY {usual}']}
    return 'TOUGH CLASS', {'lines64': lines, 'pages32': [list(CHEER_32)], 'text': ' '.join(lines)}, figure, reason, \
        _similar(facts)


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
    figures = _figures(lb, usual, 'LB', space='')
    on = facts['movement'].upper()
    if code == 'went_heavier' and not facts.get('on_movement', True):
        on = f"{facts['category'].upper()} WEIGHTS"
    # The weights on a line of their own; a name too long to fit leaves the sentence (the bars frame's
    # reason line shows it).
    if code == 'go_up_lighter':
        sentence = _parts((f'GO UP A WEIGHT ON {on}', figures, f"REPS +{facts['pct']}%."),
                          (f'GO UP A WEIGHT ON {on}', figures), ('GO UP A WEIGHT', figures))
        headline = 'GO UP A WEIGHT'
    else:
        sentence = _parts((f'HEAVIER ON {on}', figures, 'EVERY TARGET HIT.'), (f'HEAVIER ON {on}', figures),
                          ('WENT HEAVIER', figures, 'KEEP IT.'))
        headline = 'HEAVIER: KEEP'
    return headline, sentence, _bars(facts['lb'], facts['usual'], 'lb'), on, 'VS PAST CLASSES'


def _rule(code):
    if code == 'tough_class':
        return _tough
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
    reason_parts = None
    if isinstance(reason, dict):  # a bottom line with a drawing in it
        reason, reason_parts = reason['text'], reason['parts']
    if isinstance(sentence, dict):  # lines laid out by the rule itself (the tough-class cheer)
        lines64, pages32, sentence = sentence['lines64'], sentence['pages32'], sentence['text']
    else:
        if isinstance(sentence, tuple):  # parts that each start a new line
            lines = [line for part in sentence for line in wrap(part)]
            sentence = f"{sentence[0]}: {'. '.join(part.rstrip('.') for part in sentence[1:])}."  # for logs
        else:
            lines = wrap(sentence)
        lines64 = lines[:LINES_64]
        pages32 = [lines[i:i + LINES_32] for i in range(0, min(len(lines), LINES_32 * PAGES_32), LINES_32)]
    view = {'code': code, 'colour': list(COLOURS[code]), 'headline': headline, 'sentence': sentence,
            'lines64': lines64, 'pages32': pages32, 'footer': footer, 'figure': figure, 'reason': reason}
    if reason_parts:
        view['reason_parts'] = reason_parts
    return view


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
