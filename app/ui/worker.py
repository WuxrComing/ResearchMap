import uuid
from PyQt6.QtCore import QThread, pyqtSignal
from sqlmodel import Session
from app.services.storage import get_engine
from app.models.topic import Topic
from app.models.session import Session as SessionModel
from app.models.chat_message import ChatMessage
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge
from app.agents.topic_builder import TopicBuilder


class TopicBuildWorker(QThread):
    finished = pyqtSignal(str, str, int, int, list)  # topic_id, title, nodes, edges, errors
    progress = pyqtSignal(str)  # status message

    def __init__(self, title: str, description: str, parent=None,
                 topic_id: str = None, session_id: str = None):
        super().__init__(parent)
        self._title = title
        self._desc = description
        self._topic_id = topic_id
        self._session_id = session_id

    def run(self):
        self.progress.emit(f"正在为「{self._title}」生成思维导图...")

        engine = get_engine()
        topic_id = self._topic_id or uuid.uuid4().hex
        session_id = self._session_id or uuid.uuid4().hex

        if not self._topic_id:
            with Session(engine) as db:
                topic = Topic(id=topic_id, title=self._title, description=self._desc)
                db.add(topic)
                session = SessionModel(
                    id=session_id, workspace_id=topic_id, title="默认会话"
                )
                db.add(session)
                db.commit()

        builder = TopicBuilder()
        node_count, edge_count, errors = builder.build(
            topic_id, self._title, self._desc, session_id
        )

        if errors:
            error_text = "; ".join(errors)
            with Session(engine) as db:
                msg = ChatMessage(
                    id=uuid.uuid4().hex,
                    session_id=session_id,
                    role="system",
                    content=f"思维导图生成失败：{error_text}",
                )
                db.add(msg)
                db.commit()

        self.finished.emit(topic_id, self._title, node_count, edge_count, errors)

    @staticmethod
    def create_empty_workspace(title: str, description: str) -> tuple[str, str]:
        engine = get_engine()
        topic_id = uuid.uuid4().hex
        session_id = uuid.uuid4().hex
        with Session(engine) as db:
            topic = Topic(id=topic_id, title=title, description=description)
            db.add(topic)
            session = SessionModel(
                id=session_id, workspace_id=topic_id, title="默认会话"
            )
            db.add(session)

            msg = ChatMessage(
                id=uuid.uuid4().hex,
                session_id=session_id,
                role="system",
                content=f"课题「{title}」已创建。请点击「生成思维导图」或直接输入描述来初始化思维导图。",
            )
            db.add(msg)
            db.commit()
        return topic_id, session_id
