"""Algorithms implemented independently of Flask and SQLAlchemy."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import timedelta
import heapq


def merge_events(streams):
    """Merge k timestamp-sorted iterables in O(N log k)."""
    heap = []
    for source, stream in enumerate(streams):
        iterator = iter(stream)
        first = next(iterator, None)
        if first is not None:
            heapq.heappush(heap, (first['timestamp'], source, 0, first, iterator))
    result = []
    while heap:
        _, source, seq, event, iterator = heapq.heappop(heap)
        result.append(event)
        following = next(iterator, None)
        if following is not None:
            heapq.heappush(heap, (following['timestamp'], source, seq + 1, following, iterator))
    return result


def date_range(events, start, end):
    """Binary search over sorted event timestamps, O(log N + matches)."""
    timestamps = [e['timestamp'] for e in events]
    return events[bisect_left(timestamps, start):bisect_right(timestamps, end)]


def category_index(events):
    grouped = defaultdict(list)
    for event in events:
        grouped[event['kind']].append(event)
    return dict(grouped)


def glucose_rolling_averages(readings, window_minutes=60):
    """Two-pointer time window in O(N), input sorted by timestamp."""
    if window_minutes <= 0:
        raise ValueError('Window must be positive')
    left, total, result = 0, 0, []
    for right, reading in enumerate(readings):
        total += reading['value']
        cutoff = reading['timestamp'] - timedelta(minutes=window_minutes)
        while readings[left]['timestamp'] < cutoff:
            total -= readings[left]['value']
            left += 1
        result.append({'timestamp': reading['timestamp'], 'average': round(total / (right-left+1), 1)})
    return result
