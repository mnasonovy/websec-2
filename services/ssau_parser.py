import re
import time
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://ssau.ru/rasp"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}
CACHE_TTL_SECONDS = 300
_CACHE: Dict[str, Dict[str, Any]] = {}


def _cache_get(key: str) -> Optional[Any]:
    item = _CACHE.get(key)
    if item is None:
        return None

    if time.time() - item["ts"] > CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None

    return item["value"]


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = {"ts": time.time(), "value": value}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _fetch_schedule_page(group_id: str, week: Optional[int] = None) -> str:
    params = {"groupId": group_id}
    if week is not None:
        params["selectedWeek"] = week

    cache_key = f"html:{group_id}:{week}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    response.encoding = "utf-8"

    html = response.text
    _cache_set(cache_key, html)
    return html


def _extract_week_from_soup(soup: BeautifulSoup) -> Optional[int]:
    week_element = soup.select_one(".week-nav-current_week")
    if week_element is None:
        return None

    match = re.search(r"(\d+)", _clean_text(week_element.get_text()))
    return int(match.group(1)) if match else None


def get_current_week() -> int:
    group_id = get_groups()[0]["id"]
    html = _fetch_schedule_page(group_id)
    soup = BeautifulSoup(html, "lxml")
    return _extract_week_from_soup(soup) or 1


def _extract_group_meta(soup: BeautifulSoup, group_id: str) -> Dict[str, Any]:
    metadata = {
        "group_id": group_id,
        "group_name": "6413-100503D",
        "program": "10.05.03 Информационная безопасность автоматизированных систем",
        "education_form": "Специалист (Очная форма обучения)",
        "study_year_start": "01.09.2025",
    }

    info_block = soup.select_one(".info-block")
    if info_block is None:
        return metadata

    title = info_block.select_one(".info-block__title")
    if title is not None:
        metadata["group_name"] = _clean_text(title.get_text())

    description = info_block.select(".info-block__description div")
    if len(description) >= 1:
        metadata["program"] = _clean_text(description[0].get_text())
    if len(description) >= 2:
        metadata["education_form"] = _clean_text(description[1].get_text())

    semester = info_block.select_one(".info-block__semester")
    if semester is not None:
        text = _clean_text(semester.get_text())
        if "Начало учебного года:" in text:
            metadata["study_year_start"] = text.replace("Начало учебного года:", "").strip()

    return metadata


def _extract_active_week(soup: BeautifulSoup, requested_week: Optional[int]) -> int:
    if requested_week is not None:
        return requested_week
    return _extract_week_from_soup(soup) or get_current_week()


def _parse_schedule_head(schedule_items: Tag) -> List[Dict[str, str]]:
    direct_children = schedule_items.find_all(recursive=False)

    head_cells: List[Tag] = []
    for child in direct_children:
        classes = child.get("class", [])
        if "schedule__item" in classes and "schedule__head" in classes:
            head_cells.append(child)
        if len(head_cells) == 7:
            break

    if len(head_cells) < 7:
        return []

    days = []
    for cell in head_cells[1:]:
        weekday_element = cell.select_one(".schedule__head-weekday")
        date_element = cell.select_one(".schedule__head-date")

        days.append(
            {
                "day_name": _clean_text(weekday_element.get_text()).capitalize()
                if weekday_element is not None
                else "",
                "date": _clean_text(date_element.get_text()) if date_element is not None else "",
            }
        )

    return days


def _parse_teacher_text(lesson: Tag) -> str:
    teacher_block = lesson.select_one(".schedule__teacher")
    if teacher_block is None:
        return ""
    return _clean_text(teacher_block.get_text(" ", strip=True))


def _parse_groups(lesson: Tag) -> List[str]:
    group_links = lesson.select(".schedule__groups .schedule__group")
    groups = [_clean_text(link.get_text()) for link in group_links if _clean_text(link.get_text())]
    if groups:
        return groups

    groups_block = lesson.select_one(".schedule__groups")
    if groups_block is None:
        return []

    text = _clean_text(groups_block.get_text(" ", strip=True))
    return [text] if text else []


def _parse_one_lesson(lesson: Tag) -> Dict[str, Any]:
    lesson_type_element = lesson.select_one(".schedule__lesson-type-chip")
    discipline_element = lesson.select_one(".schedule__discipline")
    place_element = lesson.select_one(".schedule__place")
    teacher_link = lesson.select_one(".schedule__teacher a")

    lesson_type = _clean_text(lesson_type_element.get_text()) if lesson_type_element is not None else "Другое"
    title = _clean_text(discipline_element.get_text()) if discipline_element is not None else ""
    room = _clean_text(place_element.get_text()) if place_element is not None else ""
    teacher = _parse_teacher_text(lesson)
    groups = _parse_groups(lesson)

    staff_url = ""
    staff_id = ""

    if teacher_link is not None and teacher_link.get("href"):
        href = teacher_link["href"]
        staff_url = f"https://ssau.ru{href}" if href.startswith("/") else href

        match = re.search(r"staffId=(\d+)", href)
        if match:
            staff_id = match.group(1)

    return {
        "title": title,
        "type": lesson_type,
        "room": room,
        "teacher": teacher,
        "groups": groups,
        "staff_url": staff_url,
        "staff_id": staff_id,
    }


def _parse_schedule_item_cell(cell: Tag) -> List[Dict[str, Any]]:
    lesson_blocks = cell.find_all("div", class_="schedule__lesson", recursive=False)
    if not lesson_blocks:
        lesson_blocks = cell.select(".schedule__lesson")

    lessons = []
    for lesson in lesson_blocks:
        parsed_lesson = _parse_one_lesson(lesson)
        if parsed_lesson["title"] or parsed_lesson["teacher"] or parsed_lesson["room"]:
            lessons.append(parsed_lesson)

    return lessons


def _parse_schedule_items_dom(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    schedule_items = soup.select_one(".schedule__items")
    if schedule_items is None:
        return []

    days = _parse_schedule_head(schedule_items)
    if len(days) != 6:
        return []

    parsed_days = [
        {
            "day_name": day["day_name"],
            "date": day["date"],
            "lessons": [],
        }
        for day in days
    ]

    direct_children = schedule_items.find_all(recursive=False)

    content_children: List[Tag] = []
    head_count = 0
    for child in direct_children:
        classes = child.get("class", [])
        if "schedule__item" in classes and "schedule__head" in classes and head_count < 7:
            head_count += 1
            continue
        content_children.append(child)

    index = 0
    while index < len(content_children):
        node = content_children[index]
        classes = node.get("class", [])

        if "schedule__time" not in classes:
            index += 1
            continue

        time_items = node.select(".schedule__time-item")
        if len(time_items) < 2:
            index += 1
            continue

        start = _clean_text(time_items[0].get_text(" ", strip=True))
        end = _clean_text(time_items[1].get_text(" ", strip=True))
        time_range = f"{start} - {end}"

        day_cells = content_children[index + 1:index + 7]
        if len(day_cells) < 6:
            break

        for day_index, cell in enumerate(day_cells):
            lessons = _parse_schedule_item_cell(cell)
            for lesson in lessons:
                parsed_days[day_index]["lessons"].append(
                    {
                        "time": time_range,
                        "title": lesson["title"],
                        "type": lesson["type"],
                        "teacher": lesson["teacher"],
                        "room": lesson["room"],
                        "groups": lesson["groups"],
                        "staff_url": lesson["staff_url"],
                        "staff_id": lesson["staff_id"],
                    }
                )

        index += 7

    return parsed_days


def get_groups() -> List[Dict[str, str]]:
    return [
        {"id": "1282690301", "name": "6411-100503D"},
        {"id": "1282690279", "name": "6412-100503D"},
        {"id": "1213641978", "name": "6413-100503D"},
    ]


def get_teachers() -> List[Dict[str, str]]:
    teachers: Dict[str, Dict[str, str]] = {}

    for group in get_groups():
        for week in [31, 32, 33, 34, 35, 36, 37, 38]:
            try:
                schedule = get_schedule_by_group(group["id"], week)
            except Exception:
                continue

            for day in schedule.get("days", []):
                for lesson in day.get("lessons", []):
                    teacher = lesson.get("teacher", "").strip()
                    if teacher:
                        teachers[teacher] = {
                            "id": teacher,
                            "name": teacher,
                            "staff_url": lesson.get("staff_url", ""),
                        }

    return [teachers[name] for name in sorted(teachers)]


def get_schedule_by_group(group_id: str, week: Optional[int] = None) -> Dict[str, Any]:
    cache_key = f"parsed:{group_id}:{week}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    html = _fetch_schedule_page(group_id, week)
    soup = BeautifulSoup(html, "lxml")

    metadata = _extract_group_meta(soup, group_id)
    active_week = _extract_active_week(soup, week)

    page_text = _clean_text(soup.get_text(" ", strip=True))
    if "Расписание пока не введено" in page_text:
        result = {
            "mode": "group",
            "entity": group_id,
            "week": active_week,
            "meta": metadata,
            "days": [],
            "message": "Расписание пока не введено",
        }
        _cache_set(cache_key, result)
        return result

    schedule_days = _parse_schedule_items_dom(soup)
    if not schedule_days:
        result = {
            "mode": "group",
            "entity": group_id,
            "week": active_week,
            "meta": metadata,
            "days": [],
            "message": "Не удалось распарсить расписание",
        }
        _cache_set(cache_key, result)
        return result

    result = {
        "mode": "group",
        "entity": group_id,
        "week": active_week,
        "meta": metadata,
        "days": schedule_days,
    }
    _cache_set(cache_key, result)
    return result


def get_schedule_by_teacher(teacher_name: str, week: Optional[int] = None) -> Dict[str, Any]:
    teacher_name = (teacher_name or "").strip()
    if not teacher_name:
        return {
            "mode": "teacher",
            "entity": "",
            "week": week or get_current_week(),
            "days": [],
            "message": "Имя преподавателя не передано",
            "meta": {},
        }

    matched_days: Dict[str, Dict[str, Any]] = {}
    teacher_staff_url = ""

    for group in get_groups():
        try:
            group_schedule = get_schedule_by_group(group["id"], week)
        except Exception:
            continue

        for day in group_schedule.get("days", []):
            filtered_lessons = []
            for lesson in day.get("lessons", []):
                teacher = lesson.get("teacher", "")
                if teacher_name.lower() in teacher.lower():
                    lesson_copy = dict(lesson)
                    lesson_copy["group"] = group["name"]
                    filtered_lessons.append(lesson_copy)

                    if lesson.get("staff_url") and not teacher_staff_url:
                        teacher_staff_url = lesson["staff_url"]

            if filtered_lessons:
                key = f'{day["day_name"]}|{day["date"]}'
                if key not in matched_days:
                    matched_days[key] = {
                        "day_name": day["day_name"],
                        "date": day["date"],
                        "lessons": [],
                    }
                matched_days[key]["lessons"].extend(filtered_lessons)

    return {
        "mode": "teacher",
        "entity": teacher_name,
        "week": week or get_current_week(),
        "days": list(matched_days.values()),
        "meta": {
            "title": teacher_name,
            "subtitle": "Преподаватель Самарского университета",
            "study_year_start": "01.09.2025",
            "staff_url": teacher_staff_url,
        },
    }