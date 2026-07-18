from app.schemas.department import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.schemas.requester import RequesterCreate, RequesterRead, RequesterUpdate
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate
from app.schemas.knowledge_doc import KnowledgeDocCreate, KnowledgeDocRead
from app.schemas.task_request import TaskRequestCreate, TaskRequestRead
from app.schemas.work_order import WorkOrderCreate, WorkOrderRead, WorkOrderUpdate
from app.schemas.technician import TechnicianCreate, TechnicianRead, TechnicianUpdate
from app.schemas.daily_plan import DailyPlanCreate, DailyPlanRead, DailyPlanUpdate
from app.schemas.assignment import AssignmentCreate, AssignmentRead, AssignmentUpdate
from app.schemas.feedback import FeedbackCreate, FeedbackRead
from app.schemas.whatsapp import (
    WhatsAppInbound,
    WhatsAppMessage,
    WhatsAppTextBody,
    WhatsAppImageBody,
    WhatsAppAudioBody,
    WhatsAppInteractiveBody,
    OutboundTextMessage,
    OutboundTemplateMessage,
    OutboundInteractiveMessage,
)
from app.schemas.agents import (
    IntakeInput, IntakeOutput,
    TriageInput, TriageOutput,
    DispatchInput, DispatchOutput,
    PlanningInput, PlanningOutput,
    KnowledgeInput, KnowledgeOutput,
    AnalyticsInput, AnalyticsOutput,
    OrchestratorState,
)

__all__ = [
    "DepartmentCreate", "DepartmentRead", "DepartmentUpdate",
    "RequesterCreate", "RequesterRead", "RequesterUpdate",
    "AssetCreate", "AssetRead", "AssetUpdate",
    "KnowledgeDocCreate", "KnowledgeDocRead",
    "TaskRequestCreate", "TaskRequestRead",
    "WorkOrderCreate", "WorkOrderRead", "WorkOrderUpdate",
    "TechnicianCreate", "TechnicianRead", "TechnicianUpdate",
    "DailyPlanCreate", "DailyPlanRead", "DailyPlanUpdate",
    "AssignmentCreate", "AssignmentRead", "AssignmentUpdate",
    "FeedbackCreate", "FeedbackRead",
    "WhatsAppInbound", "WhatsAppMessage", "WhatsAppTextBody",
    "WhatsAppImageBody", "WhatsAppAudioBody", "WhatsAppInteractiveBody",
    "OutboundTextMessage", "OutboundTemplateMessage", "OutboundInteractiveMessage",
    "IntakeInput", "IntakeOutput",
    "TriageInput", "TriageOutput",
    "DispatchInput", "DispatchOutput",
    "PlanningInput", "PlanningOutput",
    "KnowledgeInput", "KnowledgeOutput",
    "AnalyticsInput", "AnalyticsOutput",
    "OrchestratorState",
]
