"""目标课程匹配与时间冲突处理。"""
import re

from . import fields


def _teacher_matches(spec, item):
    """教师配置可写单个名字、逗号分隔字符串或名字列表。"""
    wanted = spec.get("teacher")
    if not wanted:
        return True
    if isinstance(wanted, str):
        wanted = [name.strip() for name in re.split(r"[,，、]", wanted) if name.strip()]
    return set(wanted).issubset(set(fields.teacher_names(item)))


def _course_matches(spec, item):
    lesson = spec.get("lessonAssoc")
    if lesson and fields.lesson_id(item) != str(lesson):
        return False
    if spec.get("name") and fields.course_name(item) != spec["name"]:
        return False
    return _teacher_matches(spec, item)


def resolve_courses(items, specs):
    """将配置绑定到当前接口返回的课程记录，拒绝不明确的匹配。"""
    if not specs:
        raise RuntimeError("config.json 未配置 courses")
    courses = []
    for spec in specs:
        matches = [item for item in items if _course_matches(spec, item)]
        if len(matches) != 1:
            label = spec.get("name") or spec.get("lessonAssoc") or "未命名课程"
            raise RuntimeError(f"课程匹配失败：{label}，匹配数={len(matches)}")
        item = matches[0]
        courses.append({
            "spec": spec,
            "item": item,
            "id": fields.lesson_id(item),
            "selected": False,
            "blocked": False,
            "fails": 0,          # 累计失败次数，仅用于日志展示
            "last_msg": "",
        })
    return courses


def label(course):
    return (f"{fields.course_name(course['item'])}"
            f"（{fields.teacher_text(course['item'])}，lessonId={course['id']}）")


def conflict_pairs(courses):
    """两两检查目标课之间的时间冲突。"""
    pairs = []
    for index, left in enumerate(courses):
        for right in courses[index + 1:]:
            if fields.schedules_conflict(left["item"], right["item"]):
                pairs.append((left, right))
    return pairs


def refresh_selected(courses, selected_items):
    """按接口返回的已选列表更新每门课的 selected 状态。"""
    selected_ids = {fields.lesson_id(item) for item in fields.iter_items(selected_items)}
    for course in courses:
        course["selected"] = course["id"] in selected_ids


def apply_conflict_policy(courses, selected_items=()):
    """已选课程占用的时段会阻止未允许冲突的目标课。"""
    chosen = [course["item"] for course in courses if course["selected"]]
    chosen.extend(fields.iter_items(selected_items))
    for course in courses:
        course["blocked"] = (
            not course["selected"]
            and not course["spec"].get("allow_conflict", False)
            and any(fields.lesson_id(other) != course["id"]
                    and fields.schedules_conflict(course["item"], other)
                    for other in chosen)
        )


def pending_by_priority(courses):
    """本轮待尝试的课程：未选中、未被冲突阻止，按 priority 升序。"""
    pending = [c for c in courses if not c["selected"] and not c["blocked"]]
    return sorted(pending, key=lambda c: int(c["spec"].get("priority", 999)))
