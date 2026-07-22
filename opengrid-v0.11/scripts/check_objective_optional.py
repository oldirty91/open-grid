from backend.app.models import TaskCreate

task = TaskCreate.model_validate({
    "description": "Arm MAV 1",
    "specification": {
        "type": "opengrid.tasks.v1.Arm",
        "objective": None,
        "parameters": {},
    },
    "assigned_agent_id": "mavlink-reference-1",
    "created_by": "operator-ui",
})

assert task.specification.objective is None
print("objective-free Task validation passed")
