"""
Team Randomizer Service for Student Assignments and Lab Projects.

Supports generating balanced student groups with designated team leaders.
"""

import random
from services.student_service import list_all_students

def generate_teams(group_size=None, num_groups=None, class_name=None, assign_leader=True, subject_name=None, db_path=None):
    """
    Shuffles students and distributes them into balanced teams.
    Either group_size or num_groups must be provided.
    """
    students = list_all_students(class_name=class_name, db_path=db_path)
    if not students:
        raise ValueError("No students available to form teams.")

    total_students = len(students)

    if not group_size and not num_groups:
        group_size = 4  # default standard lab size

    if group_size:
        group_size = max(1, int(group_size))
        calculated_num_groups = max(1, total_students // group_size)
    else:
        calculated_num_groups = max(1, min(total_students, int(num_groups)))

    # Cryptographically secure shuffle for complete fairness
    shuffled_students = list(students)
    random.SystemRandom().shuffle(shuffled_students)

    # Initialize empty buckets
    teams = [[] for _ in range(calculated_num_groups)]

    # Round-robin distribution ensures balanced team sizes
    for idx, student in enumerate(shuffled_students):
        team_idx = idx % calculated_num_groups
        teams[team_idx].append(student)

    formatted_teams = []
    for t_idx, members in enumerate(teams, start=1):
        leader = members[0] if (assign_leader and members) else None
        team_dict = {
            "team_number": t_idx,
            "member_count": len(members),
            "leader": leader,
            "members": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "class_name": m.get("class_name", "EC"),
                    "is_leader": (leader is not None and m["id"] == leader["id"])
                }
                for m in members
            ]
        }
        formatted_teams.append(team_dict)

    # Build ready-to-share markdown text
    title_subj = f" for *{subject_name}*" if subject_name else ""
    class_tag = f" ({class_name})" if class_name else ""
    md_lines = [
        f"🎲 *PROJECT & ASSIGNMENT TEAMS{title_subj.upper()}*{class_tag}",
        f"👥 *Total Students:* {total_students} | *Teams Formed:* {len(formatted_teams)}",
        "───────────────────────────────"
    ]

    for t in formatted_teams:
        md_lines.append(f"🔷 *Team {t['team_number']}* ({t['member_count']} members):")
        if t["leader"]:
            md_lines.append(f"   👑 *Leader:* `#{t['leader']['id']:02d}` {t['leader']['name']}")
        for m in t["members"]:
            if not m["is_leader"]:
                md_lines.append(f"   • `#{m['id']:02d}` {m['name']}")
        md_lines.append("")

    formatted_markdown = "\n".join(md_lines)

    return {
        "total_students": total_students,
        "team_count": len(formatted_teams),
        "teams": formatted_teams,
        "formatted_markdown": formatted_markdown,
    }

