from pathlib import Path

from planner import calendar, graph, report
from planner.loading import load_project

DATA = Path(__file__).resolve().parent / "data" / "project.json"


def plan(project) -> dict:
    order = graph.topo_order(project)
    earliest, finish = graph.earliest_times(project, order)
    dates = calendar.assign_dates(project, earliest, finish, project.start)
    return {
        "order": order,
        "dates": dates,
        "slack": graph.slack(project, order),
        "critical": graph.critical_path(project, order),
        "levels": graph.levels(project, order),
        "load": calendar.workload_by_week(project, dates),
    }


def main() -> None:
    project = load_project(DATA)
    p = plan(project)
    end = max(last for _, last in p["dates"].values())
    print(f"{project.name}: {len(project.tasks)} tasks, {project.total_effort()} effort-days, ends {end}")
    print()
    print(report.task_table(project, p["order"], p["dates"], p["slack"]))
    print("\nCritical path:", report.path_line(p["critical"]))
    print("\nStages:\n" + report.levels_block(p["levels"]))
    print("\nGantt:\n" + report.gantt(p["order"], p["dates"]))
    print("\nWorkload (days per week):\n" + report.workload_table(p["load"], project.owners()))


if __name__ == "__main__":
    main()
