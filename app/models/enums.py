from enum import Enum


class TopicStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class NodeType(str, Enum):
    ROOT = "root"
    PROBLEM = "problem"
    METHOD = "method"
    MECHANISM = "mechanism"
    PAPER = "paper"
    IDEA = "idea"
    EXPERIMENT = "experiment"
    RISK = "risk"
    OPEN_QUESTION = "open_question"


class HeatLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    RISING = "rising"


class Maturity(str, Enum):
    EMERGING = "emerging"
    DEVELOPING = "developing"
    MATURE = "mature"
    DECLINING = "declining"


class EvidenceStrength(str, Enum):
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"


class EdgeRelation(str, Enum):
    SUPPORTS = "supports"
    ADDRESSES = "addresses"
    EXTENDS = "extends"
    CONTRADICTS = "contradicts"
    TRANSFERS_TO = "transfers_to"
    PARENT_OF = "parent_of"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class NodeStatus(str, Enum):
    ACTIVE = "active"
    MERGED = "merged"
    DEPRECATED = "deprecated"


class PaperNodeRelation(str, Enum):
    BELONGS_TO = "belongs_to"
    SUPPORTS = "supports"
    EXTENDS = "extends"
    CHALLENGES = "challenges"


class IdeaStatus(str, Enum):
    CANDIDATE = "candidate"
    PLANNED = "planned"
    TESTING = "testing"
    FAILED = "failed"
    ACCEPTED = "accepted"
