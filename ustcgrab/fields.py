"""教务接口记录字段提取。

全部是纯函数，不做 IO，接口字段名变化时只需改这里。
"""
import re


def iter_items(data):
    """从接口响应里取出课程记录列表。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "lessons", "rows", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def course_name(item):
    course = item.get("course")
    if isinstance(course, dict):
        name = course.get("nameZh") or course.get("name")
        if name:
            return name
    return item.get("nameZh") or item.get("courseNameZh") or ""


def teacher_names(item):
    """返回课程的全部教师名；真实接口可能包含多名教师。"""
    teachers = item.get("teachers") or item.get("teacherAssignmentList") or []
    names = []
    for teacher in teachers if isinstance(teachers, list) else [teachers]:
        if isinstance(teacher, dict):
            person = teacher.get("person") or teacher
            name = person.get("nameZh") or person.get("name")
        else:
            name = str(teacher)
        if name:
            names.append(str(name))
    if not names and item.get("teacherNameZh"):
        names.append(str(item["teacherNameZh"]))
    return names


def teacher_text(item):
    return ", ".join(teacher_names(item))


def text_value(value):
    if isinstance(value, dict):
        return value.get("textZh") or value.get("text") or value.get("textEn") or ""
    return str(value or "")


def expand_numbers(value):
    """解析教务系统的周次/节次表达式，如 ``2~5,7~18``。"""
    result = set()
    for part in re.split(r"[,，]", str(value or "")):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d+)\s*[~\-至]\s*(\d+)", part)
        if match:
            start, end = map(int, match.groups())
            result.update(range(min(start, end), max(start, end) + 1))
        elif part.isdigit():
            result.add(int(part))
    return result


def schedule_slots(item):
    """返回 (周次, 星期, 节次) 集合，用真实 dateTimePlace/weekText 判冲突。"""
    times = text_value(item.get("dateTimePlace") or item.get("weekDayPlaceText"))
    week_groups = text_value(item.get("weekText")).split(";")
    slots = set()
    for index, entry in enumerate(times.split(";")):
        match = re.search(r"\b([1-7])\s*\(([^)]*)\)", entry)
        if not match:
            continue
        weekday = int(match.group(1))
        units = expand_numbers(match.group(2))
        weeks = expand_numbers(week_groups[index] if index < len(week_groups) else "")
        for unit in units:
            if weeks:
                slots.update((week, weekday, unit) for week in weeks)
            else:
                slots.add((None, weekday, unit))
    return slots


def schedules_conflict(left, right):
    """判断两课是否存在同一周、星期、节次重叠。"""
    for l_week, l_day, l_unit in schedule_slots(left):
        for r_week, r_day, r_unit in schedule_slots(right):
            same_slot = l_day == r_day and l_unit == r_unit
            if same_slot and (l_week is None or r_week is None or l_week == r_week):
                return True
    return False


def limit_of(item):
    """容量上限；接口可能不给，仅用于展示。"""
    return item.get("limitCount") or item.get("capacity") or 0


def lesson_id(item):
    return str(item.get("id") or item.get("lessonId") or "")
