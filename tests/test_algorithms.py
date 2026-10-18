from datetime import datetime, timezone, timedelta
from algorithms import merge_events, date_range, category_index, glucose_rolling_averages

def t(hour):
    return datetime(2026, 1, 1, hour, tzinfo=timezone.utc)

def test_merge_sorted():
    a = [{'timestamp':t(8),'kind':'glucose'}, {'timestamp':t(10),'kind':'glucose'}]
    b = [{'timestamp':t(9),'kind':'meal'}]
    assert [x['timestamp'].hour for x in merge_events([a,b])] == [8,9,10]

def test_empty_and_ties():
    assert merge_events([[],[]]) == []
    assert len(merge_events([[{'timestamp':t(8)}],[{'timestamp':t(8)}]])) == 2

def test_binary_range():
    items = merge_events([[{'timestamp':t(i),'kind':'glucose'} for i in (8,9,10)]])
    assert [x['timestamp'].hour for x in date_range(items,t(9),t(10))] == [9,10]
    assert len(category_index(items)['glucose']) == 3

def test_rolling():
    r = [{'timestamp':t(8),'value':100},{'timestamp':t(9),'value':140},{'timestamp':t(10),'value':160}]
    assert [x['average'] for x in glucose_rolling_averages(r,60)] == [100,120,150]
