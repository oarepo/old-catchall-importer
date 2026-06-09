import datetime
import enum
import uuid
from typing import Any, Optional

from sqlalchemy import (
    ARRAY,
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql.sqltypes import NullType


class Base(DeclarativeBase):
    pass


class Termstatusenum(str, enum.Enum):
    ALIVE = "alive"
    DELETED = "deleted"
    DELETE_PENDING = "delete_pending"


class AccessActionssystemroles(Base):
    __tablename__ = "access_actionssystemroles"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_access_actionssystemroles"),
        UniqueConstraint(
            "action",
            "exclude",
            "argument",
            "role_name",
            name="access_actionssystemroles_unique",
        ),
        Index("ix_access_actionssystemroles_action", "action"),
        Index("ix_access_actionssystemroles_argument", "argument"),
        Index("ix_access_actionssystemroles_role_name", "role_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exclude: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    role_name: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[Optional[str]] = mapped_column(String(80))
    argument: Mapped[Optional[str]] = mapped_column(String(255))


class AccountsRole(Base):
    __tablename__ = "accounts_role"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_accounts_role"),
        UniqueConstraint("name", name="uq_accounts_role_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(80))
    description: Mapped[Optional[str]] = mapped_column(String(255))

    user: Mapped[list["AccountsUser"]] = relationship(
        "AccountsUser", secondary="accounts_userrole", back_populates="role"
    )
    group: Mapped[list["CesnetGroup"]] = relationship(
        "CesnetGroup", secondary="cesnet_group_roles", back_populates="role"
    )
    community: Mapped[list["OarepoCommunities"]] = relationship(
        "OarepoCommunities", secondary="oarepo_communities_role", back_populates="role"
    )
    access_actionsroles: Mapped[list["AccessActionsroles"]] = relationship(
        "AccessActionsroles", back_populates="role"
    )


class AccountsUser(Base):
    __tablename__ = "accounts_user"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_accounts_user"),
        UniqueConstraint("email", name="uq_accounts_user_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    password: Mapped[Optional[str]] = mapped_column(String(255))
    active: Mapped[Optional[bool]] = mapped_column(Boolean)
    confirmed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    current_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(50))
    current_login_ip: Mapped[Optional[str]] = mapped_column(String(50))
    login_count: Mapped[Optional[int]] = mapped_column(Integer)

    role: Mapped[list["AccountsRole"]] = relationship(
        "AccountsRole", secondary="accounts_userrole", back_populates="user"
    )
    access_actionsusers: Mapped[list["AccessActionsusers"]] = relationship(
        "AccessActionsusers", back_populates="user"
    )
    accounts_user_session_activity: Mapped[list["AccountsUserSessionActivity"]] = (
        relationship("AccountsUserSessionActivity", back_populates="user")
    )
    enrollment_enrolled_user: Mapped[list["Enrollment"]] = relationship(
        "Enrollment",
        foreign_keys="[Enrollment.enrolled_user]",
        back_populates="accounts_user",
    )
    enrollment_granting_user: Mapped[list["Enrollment"]] = relationship(
        "Enrollment",
        foreign_keys="[Enrollment.granting_user]",
        back_populates="accounts_user_",
    )
    enrollment_revoker: Mapped[list["Enrollment"]] = relationship(
        "Enrollment",
        foreign_keys="[Enrollment.revoker]",
        back_populates="accounts_user1",
    )
    oauth2server_client: Mapped[list["Oauth2serverClient"]] = relationship(
        "Oauth2serverClient", back_populates="user"
    )
    oauthclient_remoteaccount: Mapped[list["OauthclientRemoteaccount"]] = relationship(
        "OauthclientRemoteaccount", back_populates="user"
    )
    oauthclient_useridentity: Mapped[list["OauthclientUseridentity"]] = relationship(
        "OauthclientUseridentity", back_populates="accounts_user"
    )
    transaction: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="user"
    )
    oauth2server_token: Mapped[list["Oauth2serverToken"]] = relationship(
        "Oauth2serverToken", back_populates="user"
    )


class CesnetGroup(Base):
    __tablename__ = "cesnet_group"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_cesnet_group"),
        UniqueConstraint("uri", name="uq_cesnet_group_uri"),
        Index("ix_cesnet_group_uuid", "uuid", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))

    role: Mapped[list["AccountsRole"]] = relationship(
        "AccountsRole", secondary="cesnet_group_roles", back_populates="group"
    )


class FilesFiles(Base):
    __tablename__ = "files_files"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_files_files"),
        UniqueConstraint("uri", name="uq_files_files_uri"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    readable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    writable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    uri: Mapped[Optional[str]] = mapped_column(Text)
    storage_class: Mapped[Optional[str]] = mapped_column(String(1))
    size: Mapped[Optional[int]] = mapped_column(BigInteger)
    checksum: Mapped[Optional[str]] = mapped_column(String(255))
    last_check_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    last_check: Mapped[Optional[bool]] = mapped_column(Boolean)

    files_multipartobject: Mapped[list["FilesMultipartobject"]] = relationship(
        "FilesMultipartobject", back_populates="file"
    )
    files_object: Mapped[list["FilesObject"]] = relationship(
        "FilesObject", back_populates="file"
    )


class FilesLocation(Base):
    __tablename__ = "files_location"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_files_location"),
        UniqueConstraint("name", name="uq_files_location_name"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    uri: Mapped[str] = mapped_column(String(255), nullable=False)
    default: Mapped[bool] = mapped_column(Boolean, nullable=False)

    files_bucket: Mapped[list["FilesBucket"]] = relationship(
        "FilesBucket", back_populates="files_location"
    )


class OaiserverSet(Base):
    __tablename__ = "oaiserver_set"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_oaiserver_set"),
        UniqueConstraint("spec", name="uq_oaiserver_set_spec"),
        Index("ix_oaiserver_set_name", "name"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spec: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    search_pattern: Mapped[Optional[str]] = mapped_column(Text)


class OarepoCommunities(Base):
    __tablename__ = "oarepo_communities"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_oarepo_communities"),)

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[str] = mapped_column(String(63), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(128))
    json: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_deleted: Mapped[Optional[bool]] = mapped_column(Boolean)

    role: Mapped[list["AccountsRole"]] = relationship(
        "AccountsRole", secondary="oarepo_communities_role", back_populates="community"
    )


class OarepoOaiSync(Base):
    __tablename__ = "oarepo_oai_sync"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_oarepo_oai_sync"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_code: Mapped[str] = mapped_column(String, nullable=False)
    synchronizer_code: Mapped[Optional[str]] = mapped_column(String)
    purpose: Mapped[Optional[str]] = mapped_column(String)
    sync_start: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    sync_end: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    status: Mapped[Optional[str]] = mapped_column(String(32))
    logs: Mapped[Optional[str]] = mapped_column(Text)
    records_created: Mapped[Optional[int]] = mapped_column(Integer)
    records_modified: Mapped[Optional[int]] = mapped_column(Integer)
    records_deleted: Mapped[Optional[int]] = mapped_column(Integer)

    oai_record_exc: Mapped[list["OaiRecordExc"]] = relationship(
        "OaiRecordExc", back_populates="oai_sync"
    )
    oarepo_oai_record_creation_sync: Mapped[list["OarepoOaiRecord"]] = relationship(
        "OarepoOaiRecord",
        foreign_keys="[OarepoOaiRecord.creation_sync_id]",
        back_populates="creation_sync",
    )
    oarepo_oai_record_last_sync: Mapped[list["OarepoOaiRecord"]] = relationship(
        "OarepoOaiRecord",
        foreign_keys="[OarepoOaiRecord.last_sync_id]",
        back_populates="last_sync",
    )
    oarepo_oai_record_modification_sync: Mapped[list["OarepoOaiRecord"]] = relationship(
        "OarepoOaiRecord",
        foreign_keys="[OarepoOaiRecord.modification_sync_id]",
        back_populates="modification_sync",
    )


class OarepoReferencesClassname(Base):
    __tablename__ = "oarepo_references_classname"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_oarepo_references_classname"),
        Index("ix_oarepo_references_classname_name", "name", unique=True),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String)

    oarepo_references_referencing_record: Mapped[
        list["OarepoReferencesReferencingRecord"]
    ] = relationship("OarepoReferencesReferencingRecord", back_populates="class_")


class OarepoReferencesVersion(Base):
    __tablename__ = "oarepo_references_version"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id", "transaction_id", name="pk_oarepo_references_version"
        ),
        Index("ix_oarepo_references_version_end_transaction_id", "end_transaction_id"),
        Index("ix_oarepo_references_version_operation_type", "operation_type"),
        Index("ix_oarepo_references_version_reference", "reference"),
        Index("ix_oarepo_references_version_reference_uuid", "reference_uuid"),
        Index("ix_oarepo_references_version_transaction_id", "transaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    operation_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    updated: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    record_id: Mapped[Optional[int]] = mapped_column(Integer)
    reference: Mapped[Optional[str]] = mapped_column(String(255))
    reference_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    inline: Mapped[Optional[bool]] = mapped_column(Boolean)
    version_id: Mapped[Optional[int]] = mapped_column(Integer)
    end_transaction_id: Mapped[Optional[int]] = mapped_column(BigInteger)


class OarepoTokens(Base):
    __tablename__ = "oarepo_tokens"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_oarepo_tokens"),
        Index("idx_rec_uuid", "rec_uuid"),
        Index("uidx_token", "token", unique=True),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    rec_uuid: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    not_after: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)


class PidstorePid(Base):
    __tablename__ = "pidstore_pid"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_pidstore_pid"),
        Index("idx_object", "object_type", "object_uuid"),
        Index("idx_status", "status"),
        Index("uidx_type_pid", "pid_type", "pid_value", unique=True),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pid_type: Mapped[str] = mapped_column(String(6), nullable=False)
    pid_value: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    pid_provider: Mapped[Optional[str]] = mapped_column(String(8))
    object_type: Mapped[Optional[str]] = mapped_column(String(3))
    object_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    pidstore_redirect: Mapped[list["PidstoreRedirect"]] = relationship(
        "PidstoreRedirect", back_populates="pid"
    )


class PidstoreRecid(Base):
    __tablename__ = "pidstore_recid"
    __table_args__ = (PrimaryKeyConstraint("recid", name="pk_pidstore_recid"),)

    recid: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class RecordsMetadata(Base):
    __tablename__ = "records_metadata"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_records_metadata"),)

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    json: Mapped[Optional[dict]] = mapped_column(JSONB)

    bucket: Mapped[list["FilesBucket"]] = relationship(
        "FilesBucket", secondary="records_buckets", back_populates="record"
    )


class RecordsMetadataVersion(Base):
    __tablename__ = "records_metadata_version"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id", "transaction_id", name="pk_records_metadata_version"
        ),
        Index("ix_records_metadata_version_end_transaction_id", "end_transaction_id"),
        Index("ix_records_metadata_version_operation_type", "operation_type"),
        Index("ix_records_metadata_version_transaction_id", "transaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    operation_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    updated: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    json: Mapped[Optional[dict]] = mapped_column(JSONB)
    version_id: Mapped[Optional[int]] = mapped_column(Integer)
    end_transaction_id: Mapped[Optional[int]] = mapped_column(BigInteger)


class TaxonomyTaxonomy(Base):
    __tablename__ = "taxonomy_taxonomy"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="taxonomy_taxonomy_pkey"),
        Index("ix_taxonomy_taxonomy_code", "code", unique=True),
        Index("ix_taxonomy_taxonomy_url", "url", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[Optional[str]] = mapped_column(String(256))
    url: Mapped[Optional[str]] = mapped_column(String(1024))
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    select: Mapped[Optional[dict]] = mapped_column(JSONB)

    taxonomy_term: Mapped[list["TaxonomyTerm"]] = relationship(
        "TaxonomyTerm", back_populates="taxonomy"
    )


class AccessActionsroles(Base):
    __tablename__ = "access_actionsroles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["role_id"],
            ["accounts_role.id"],
            ondelete="CASCADE",
            name="fk_access_actionsroles_role_id_accounts_role",
        ),
        PrimaryKeyConstraint("id", name="pk_access_actionsroles"),
        UniqueConstraint(
            "action",
            "exclude",
            "argument",
            "role_id",
            name="access_actionsroles_unique",
        ),
        Index("ix_access_actionsroles_action", "action"),
        Index("ix_access_actionsroles_argument", "argument"),
        Index("ix_access_actionsroles_role_id", "role_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exclude: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    role_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[Optional[str]] = mapped_column(String(80))
    argument: Mapped[Optional[str]] = mapped_column(String(255))

    role: Mapped["AccountsRole"] = relationship(
        "AccountsRole", back_populates="access_actionsroles"
    )


class AccessActionsusers(Base):
    __tablename__ = "access_actionsusers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["accounts_user.id"],
            ondelete="CASCADE",
            name="fk_access_actionsusers_user_id_accounts_user",
        ),
        PrimaryKeyConstraint("id", name="pk_access_actionsusers"),
        UniqueConstraint(
            "action",
            "exclude",
            "argument",
            "user_id",
            name="access_actionsusers_unique",
        ),
        Index("ix_access_actionsusers_action", "action"),
        Index("ix_access_actionsusers_argument", "argument"),
        Index("ix_access_actionsusers_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exclude: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[Optional[str]] = mapped_column(String(80))
    argument: Mapped[Optional[str]] = mapped_column(String(255))

    user: Mapped["AccountsUser"] = relationship(
        "AccountsUser", back_populates="access_actionsusers"
    )


class AccountsUserSessionActivity(Base):
    __tablename__ = "accounts_user_session_activity"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["accounts_user.id"],
            name="fk_accounts_session_activity_user_id",
        ),
        PrimaryKeyConstraint("sid_s", name="pk_accounts_user_session_activity"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    sid_s: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    ip: Mapped[Optional[str]] = mapped_column(String(80))
    country: Mapped[Optional[str]] = mapped_column(String(3))
    browser: Mapped[Optional[str]] = mapped_column(String(80))
    browser_version: Mapped[Optional[str]] = mapped_column(String(30))
    os: Mapped[Optional[str]] = mapped_column(String(80))
    device: Mapped[Optional[str]] = mapped_column(String(80))

    user: Mapped[Optional["AccountsUser"]] = relationship(
        "AccountsUser", back_populates="accounts_user_session_activity"
    )


t_accounts_userrole = Table(
    "accounts_userrole",
    Base.metadata,
    Column("user_id", Integer),
    Column("role_id", Integer),
    ForeignKeyConstraint(
        ["role_id"], ["accounts_role.id"], name="fk_accounts_userrole_role_id"
    ),
    ForeignKeyConstraint(
        ["user_id"], ["accounts_user.id"], name="fk_accounts_userrole_user_id"
    ),
)


t_cesnet_group_roles = Table(
    "cesnet_group_roles",
    Base.metadata,
    Column("group_id", Integer),
    Column("role_id", Integer),
    ForeignKeyConstraint(
        ["group_id"], ["cesnet_group.id"], name="fk_cesnet_group_roles_group_id"
    ),
    ForeignKeyConstraint(
        ["role_id"], ["accounts_role.id"], name="fk_cesnet_group_roles_role_id"
    ),
)


class Enrollment(Base):
    __tablename__ = "enrollment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["enrolled_user"],
            ["accounts_user.id"],
            name="fk_enrollment_enrolled_user_accounts_user",
        ),
        ForeignKeyConstraint(
            ["granting_user"],
            ["accounts_user.id"],
            name="fk_enrollment_granting_user_accounts_user",
        ),
        ForeignKeyConstraint(
            ["parent_enrollment"],
            ["enrollment.id"],
            name="fk_enrollment_parent_enrollment_enrollment",
        ),
        ForeignKeyConstraint(
            ["revoker"],
            ["accounts_user.id"],
            name="fk_enrollment_revoker_accounts_user",
        ),
        PrimaryKeyConstraint("id", name="pk_enrollment"),
        UniqueConstraint("key", name="uq_enrollment_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enrollment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    enrolled_email: Mapped[str] = mapped_column(String(128), nullable=False)
    granting_user: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(255), nullable=False)
    start_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    external_key: Mapped[Optional[str]] = mapped_column(String(100))
    enrolled_user: Mapped[Optional[int]] = mapped_column(Integer)
    granting_email: Mapped[Optional[str]] = mapped_column(String(128))
    revoker: Mapped[Optional[int]] = mapped_column(Integer)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    actions: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String()))
    expiration_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    user_attached_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime
    )
    accepted_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    rejected_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    finalization_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime
    )
    revocation_timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    accept_url: Mapped[Optional[str]] = mapped_column(String(256))
    reject_url: Mapped[Optional[str]] = mapped_column(String(256))
    success_url: Mapped[Optional[str]] = mapped_column(String(256))
    failure_url: Mapped[Optional[str]] = mapped_column(String(256))
    parent_enrollment: Mapped[Optional[int]] = mapped_column(Integer)

    accounts_user: Mapped[Optional["AccountsUser"]] = relationship(
        "AccountsUser",
        foreign_keys=[enrolled_user],
        back_populates="enrollment_enrolled_user",
    )
    accounts_user_: Mapped["AccountsUser"] = relationship(
        "AccountsUser",
        foreign_keys=[granting_user],
        back_populates="enrollment_granting_user",
    )
    enrollment: Mapped[Optional["Enrollment"]] = relationship(
        "Enrollment", remote_side=[id], back_populates="enrollment_reverse"
    )
    enrollment_reverse: Mapped[list["Enrollment"]] = relationship(
        "Enrollment", remote_side=[parent_enrollment], back_populates="enrollment"
    )
    accounts_user1: Mapped[Optional["AccountsUser"]] = relationship(
        "AccountsUser", foreign_keys=[revoker], back_populates="enrollment_revoker"
    )


class FilesBucket(Base):
    __tablename__ = "files_bucket"
    __table_args__ = (
        ForeignKeyConstraint(
            ["default_location"],
            ["files_location.id"],
            ondelete="RESTRICT",
            name="fk_files_bucket_default_location_files_location",
        ),
        PrimaryKeyConstraint("id", name="pk_files_bucket"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    default_location: Mapped[int] = mapped_column(Integer, nullable=False)
    default_storage_class: Mapped[str] = mapped_column(String(1), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quota_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    max_file_size: Mapped[Optional[int]] = mapped_column(BigInteger)

    files_location: Mapped["FilesLocation"] = relationship(
        "FilesLocation", back_populates="files_bucket"
    )
    record: Mapped[list["RecordsMetadata"]] = relationship(
        "RecordsMetadata", secondary="records_buckets", back_populates="bucket"
    )
    files_buckettags: Mapped[list["FilesBuckettags"]] = relationship(
        "FilesBuckettags", back_populates="bucket"
    )
    files_multipartobject: Mapped[list["FilesMultipartobject"]] = relationship(
        "FilesMultipartobject", back_populates="bucket"
    )
    files_object: Mapped[list["FilesObject"]] = relationship(
        "FilesObject", back_populates="bucket"
    )


class OaiRecordExc(Base):
    __tablename__ = "oai_record_exc"
    __table_args__ = (
        ForeignKeyConstraint(
            ["oai_sync_id"],
            ["oarepo_oai_sync.id"],
            name="fk_oai_record_exc_oai_sync_id_oarepo_oai_sync",
        ),
        PrimaryKeyConstraint("id", name="pk_oai_record_exc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    oai_identifier: Mapped[str] = mapped_column(String, nullable=False)
    traceback: Mapped[Optional[str]] = mapped_column(Text)
    oai_sync_id: Mapped[Optional[int]] = mapped_column(Integer)

    oai_sync: Mapped[Optional["OarepoOaiSync"]] = relationship(
        "OarepoOaiSync", back_populates="oai_record_exc"
    )


t_oarepo_communities_role = Table(
    "oarepo_communities_role",
    Base.metadata,
    Column("community_id", String(63)),
    Column("role_id", Integer),
    ForeignKeyConstraint(
        ["community_id"],
        ["oarepo_communities.id"],
        name="fk_oarepo_communities_role_community_id",
    ),
    ForeignKeyConstraint(
        ["role_id"], ["accounts_role.id"], name="fk_oarepo_communities_role_role_id"
    ),
    UniqueConstraint("role_id", name="uq_oarepo_communities_role_role_id"),
)


class OarepoOaiRecord(RecordsMetadata):
    __tablename__ = "oarepo_oai_record"
    __table_args__ = (
        ForeignKeyConstraint(
            ["creation_sync_id"],
            ["oarepo_oai_sync.id"],
            name="fk_oarepo_oai_record_creation_sync_id_oarepo_oai_sync",
        ),
        ForeignKeyConstraint(
            ["id"],
            ["records_metadata.id"],
            name="fk_oarepo_oai_record_id_records_metadata",
        ),
        ForeignKeyConstraint(
            ["last_sync_id"],
            ["oarepo_oai_sync.id"],
            name="fk_oarepo_oai_record_last_sync_id_oarepo_oai_sync",
        ),
        ForeignKeyConstraint(
            ["modification_sync_id"],
            ["oarepo_oai_sync.id"],
            name="fk_oarepo_oai_record_modification_sync_id_oarepo_oai_sync",
        ),
        PrimaryKeyConstraint("id", name="pk_oarepo_oai_record"),
        UniqueConstraint("oai_identifier", name="uq_oarepo_oai_record_oai_identifier"),
        UniqueConstraint("pid", name="uq_oarepo_oai_record_pid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    pid: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    oai_identifier: Mapped[Optional[str]] = mapped_column(String(2048))
    last_sync_id: Mapped[Optional[int]] = mapped_column(Integer)
    modification_sync_id: Mapped[Optional[int]] = mapped_column(Integer)
    creation_sync_id: Mapped[Optional[int]] = mapped_column(Integer)

    creation_sync: Mapped[Optional["OarepoOaiSync"]] = relationship(
        "OarepoOaiSync",
        foreign_keys=[creation_sync_id],
        back_populates="oarepo_oai_record_creation_sync",
    )
    last_sync: Mapped[Optional["OarepoOaiSync"]] = relationship(
        "OarepoOaiSync",
        foreign_keys=[last_sync_id],
        back_populates="oarepo_oai_record_last_sync",
    )
    modification_sync: Mapped[Optional["OarepoOaiSync"]] = relationship(
        "OarepoOaiSync",
        foreign_keys=[modification_sync_id],
        back_populates="oarepo_oai_record_modification_sync",
    )
    oarepo_oai_identifiers: Mapped[list["OarepoOaiIdentifiers"]] = relationship(
        "OarepoOaiIdentifiers", back_populates="oai_record"
    )


class OarepoReferencesReferencingRecord(Base):
    __tablename__ = "oarepo_references_referencing_record"
    __table_args__ = (
        ForeignKeyConstraint(
            ["class_id"],
            ["oarepo_references_classname.id"],
            ondelete="CASCADE",
            name="fk_oarepo_references_class_id_classname",
        ),
        PrimaryKeyConstraint("id", name="pk_oarepo_references_referencing_record"),
        Index(
            "ix_oarepo_references_referencing_record_record_uuid",
            "record_uuid",
            unique=True,
        ),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    class_id: Mapped[Optional[int]] = mapped_column(Integer)

    class_: Mapped[Optional["OarepoReferencesClassname"]] = relationship(
        "OarepoReferencesClassname",
        back_populates="oarepo_references_referencing_record",
    )
    oarepo_references: Mapped[list["OarepoReferences"]] = relationship(
        "OarepoReferences", back_populates="record"
    )


class Oauth2serverClient(Base):
    __tablename__ = "oauth2server_client"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["accounts_user.id"],
            ondelete="CASCADE",
            name="fk_oauth2server_client_user_id_accounts_user",
        ),
        PrimaryKeyConstraint("client_id", name="pk_oauth2server_client"),
        Index("ix_oauth2server_client_client_secret", "client_secret", unique=True),
        Index("ix_oauth2server_client_user_id", "user_id"),
    )

    client_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    client_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(40))
    description: Mapped[Optional[str]] = mapped_column(Text)
    website: Mapped[Optional[str]] = mapped_column(String)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    is_confidential: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_internal: Mapped[Optional[bool]] = mapped_column(Boolean)
    _redirect_uris: Mapped[Optional[str]] = mapped_column(Text)
    _default_scopes: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[Optional["AccountsUser"]] = relationship(
        "AccountsUser", back_populates="oauth2server_client"
    )
    oauth2server_token: Mapped[list["Oauth2serverToken"]] = relationship(
        "Oauth2serverToken", back_populates="client"
    )


class OauthclientRemoteaccount(Base):
    __tablename__ = "oauthclient_remoteaccount"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["accounts_user.id"],
            name="fk_oauthclient_remoteaccount_user_id_accounts_user",
        ),
        PrimaryKeyConstraint("id", name="pk_oauthclient_remoteaccount"),
        UniqueConstraint(
            "user_id", "client_id", name="uq_oauthclient_remoteaccount_user_id"
        ),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    extra_data: Mapped[dict] = mapped_column(JSON, nullable=False)

    user: Mapped["AccountsUser"] = relationship(
        "AccountsUser", back_populates="oauthclient_remoteaccount"
    )
    oauthclient_remotetoken: Mapped[list["OauthclientRemotetoken"]] = relationship(
        "OauthclientRemotetoken", back_populates="oauthclient_remoteaccount"
    )


class OauthclientUseridentity(Base):
    __tablename__ = "oauthclient_useridentity"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id_user"],
            ["accounts_user.id"],
            name="fk_oauthclient_useridentity_id_user_accounts_user",
        ),
        PrimaryKeyConstraint("id", "method", name="pk_oauthclient_useridentity"),
        Index("useridentity_id_user_method", "id_user", "method", unique=True),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    method: Mapped[str] = mapped_column(String(255), primary_key=True)
    id_user: Mapped[int] = mapped_column(Integer, nullable=False)

    accounts_user: Mapped["AccountsUser"] = relationship(
        "AccountsUser", back_populates="oauthclient_useridentity"
    )


class PidstoreRedirect(Base):
    __tablename__ = "pidstore_redirect"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pid_id"],
            ["pidstore_pid.id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
            name="fk_pidstore_redirect_pid_id_pidstore_pid",
        ),
        PrimaryKeyConstraint("id", name="pk_pidstore_redirect"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    pid_id: Mapped[int] = mapped_column(Integer, nullable=False)

    pid: Mapped["PidstorePid"] = relationship(
        "PidstorePid", back_populates="pidstore_redirect"
    )


class TaxonomyTerm(Base):
    __tablename__ = "taxonomy_term"
    __table_args__ = (
        ForeignKeyConstraint(
            ["obsoleted_by_id"],
            ["taxonomy_term.id"],
            name="taxonomy_term_obsoleted_by_id_fkey",
        ),
        ForeignKeyConstraint(
            ["parent_id"], ["taxonomy_term.id"], name="taxonomy_term_parent_id_fkey"
        ),
        ForeignKeyConstraint(
            ["taxonomy_id"],
            ["taxonomy_taxonomy.id"],
            name="taxonomy_term_taxonomy_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="taxonomy_term_pkey"),
        UniqueConstraint("taxonomy_id", "slug", name="unique_taxonomy_slug"),
        Index("index_term_slug", "slug", postgresql_using="gist"),
        Index("ix_taxonomy_term_slug", "slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[Termstatusenum] = mapped_column(
        Enum(
            Termstatusenum,
            values_callable=lambda cls: [member.value for member in cls],
            name="termstatusenum",
        ),
        nullable=False,
    )
    slug: Mapped[Optional[str]] = mapped_column(String)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    level: Mapped[Optional[int]] = mapped_column(Integer)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer)
    taxonomy_id: Mapped[Optional[int]] = mapped_column(Integer)
    taxonomy_code: Mapped[Optional[str]] = mapped_column(String(256))
    busy_count: Mapped[Optional[int]] = mapped_column(Integer)
    obsoleted_by_id: Mapped[Optional[int]] = mapped_column(Integer)

    obsoleted_by: Mapped[Optional["TaxonomyTerm"]] = relationship(
        "TaxonomyTerm",
        remote_side=[id],
        foreign_keys=[obsoleted_by_id],
        back_populates="obsoleted_by_reverse",
    )
    obsoleted_by_reverse: Mapped[list["TaxonomyTerm"]] = relationship(
        "TaxonomyTerm",
        remote_side=[obsoleted_by_id],
        foreign_keys=[obsoleted_by_id],
        back_populates="obsoleted_by",
    )
    parent: Mapped[Optional["TaxonomyTerm"]] = relationship(
        "TaxonomyTerm",
        remote_side=[id],
        foreign_keys=[parent_id],
        back_populates="parent_reverse",
    )
    parent_reverse: Mapped[list["TaxonomyTerm"]] = relationship(
        "TaxonomyTerm",
        remote_side=[parent_id],
        foreign_keys=[parent_id],
        back_populates="parent",
    )
    taxonomy: Mapped[Optional["TaxonomyTaxonomy"]] = relationship(
        "TaxonomyTaxonomy", back_populates="taxonomy_term"
    )


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["accounts_user.id"],
            name="fk_transaction_user_id_accounts_user",
        ),
        PrimaryKeyConstraint("id", name="pk_transaction"),
        Index("ix_transaction_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    issued_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    remote_addr: Mapped[Optional[str]] = mapped_column(String(50))
    user_id: Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped[Optional["AccountsUser"]] = relationship(
        "AccountsUser", back_populates="transaction"
    )


class FilesBuckettags(Base):
    __tablename__ = "files_buckettags"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bucket_id"],
            ["files_bucket.id"],
            ondelete="CASCADE",
            name="fk_files_buckettags_bucket_id_files_bucket",
        ),
        PrimaryKeyConstraint("bucket_id", "key", name="pk_files_buckettags"),
    )

    bucket_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    bucket: Mapped["FilesBucket"] = relationship(
        "FilesBucket", back_populates="files_buckettags"
    )


class FilesMultipartobject(Base):
    __tablename__ = "files_multipartobject"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bucket_id"],
            ["files_bucket.id"],
            ondelete="RESTRICT",
            name="fk_files_multipartobject_bucket_id_files_bucket",
        ),
        ForeignKeyConstraint(
            ["file_id"],
            ["files_files.id"],
            ondelete="RESTRICT",
            name="fk_files_multipartobject_file_id_files_files",
        ),
        PrimaryKeyConstraint("upload_id", name="pk_files_multipartobject"),
        UniqueConstraint("upload_id", "bucket_id", "key", name="uix_item"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    upload_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    file_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bucket_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    key: Mapped[Optional[str]] = mapped_column(Text)
    chunk_size: Mapped[Optional[int]] = mapped_column(Integer)
    size: Mapped[Optional[int]] = mapped_column(BigInteger)

    bucket: Mapped[Optional["FilesBucket"]] = relationship(
        "FilesBucket", back_populates="files_multipartobject"
    )
    file: Mapped["FilesFiles"] = relationship(
        "FilesFiles", back_populates="files_multipartobject"
    )
    files_multipartobject_part: Mapped[list["FilesMultipartobjectPart"]] = relationship(
        "FilesMultipartobjectPart", back_populates="upload"
    )


class FilesObject(Base):
    __tablename__ = "files_object"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bucket_id"],
            ["files_bucket.id"],
            ondelete="RESTRICT",
            name="fk_files_object_bucket_id_files_bucket",
        ),
        ForeignKeyConstraint(
            ["file_id"],
            ["files_files.id"],
            ondelete="RESTRICT",
            name="fk_files_object_file_id_files_files",
        ),
        PrimaryKeyConstraint("version_id", name="pk_files_object"),
        UniqueConstraint(
            "bucket_id", "version_id", "key", name="uq_files_object_bucket_id"
        ),
        Index("ix_files_object__mimetype", "_mimetype"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    bucket_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    is_head: Mapped[bool] = mapped_column(Boolean, nullable=False)
    file_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    _mimetype: Mapped[Optional[str]] = mapped_column(String(255))

    bucket: Mapped["FilesBucket"] = relationship(
        "FilesBucket", back_populates="files_object"
    )
    file: Mapped[Optional["FilesFiles"]] = relationship(
        "FilesFiles", back_populates="files_object"
    )
    files_objecttags: Mapped[list["FilesObjecttags"]] = relationship(
        "FilesObjecttags", back_populates="version"
    )


class OarepoOaiIdentifiers(Base):
    __tablename__ = "oarepo_oai_identifiers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["oai_record_id"],
            ["oarepo_oai_record.id"],
            name="fk_oarepo_oai_identifiers_oai_record_id_oarepo_oai_record",
        ),
        PrimaryKeyConstraint("id", name="pk_oarepo_oai_identifiers"),
        UniqueConstraint(
            "oai_identifier", name="uq_oarepo_oai_identifiers_oai_identifier"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    oai_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    oai_identifier: Mapped[Optional[str]] = mapped_column(String(2048))

    oai_record: Mapped[Optional["OarepoOaiRecord"]] = relationship(
        "OarepoOaiRecord", back_populates="oarepo_oai_identifiers"
    )


class OarepoReferences(Base):
    __tablename__ = "oarepo_references"
    __table_args__ = (
        ForeignKeyConstraint(
            ["record_id"],
            ["oarepo_references_referencing_record.id"],
            ondelete="CASCADE",
            name="fk_oarepo_references_record_id_record",
        ),
        PrimaryKeyConstraint("id", name="pk_oarepo_references"),
        UniqueConstraint(
            "record_id", "reference", name="uq_oarepo_references_record_id_reference"
        ),
        Index("ix_oarepo_references_reference", "reference"),
        Index("ix_oarepo_references_reference_uuid", "reference_uuid"),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    reference: Mapped[str] = mapped_column(String(255), nullable=False)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    record_id: Mapped[Optional[int]] = mapped_column(Integer)
    reference_uuid: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    inline: Mapped[Optional[bool]] = mapped_column(Boolean)

    record: Mapped[Optional["OarepoReferencesReferencingRecord"]] = relationship(
        "OarepoReferencesReferencingRecord", back_populates="oarepo_references"
    )


class Oauth2serverToken(Base):
    __tablename__ = "oauth2server_token"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id"],
            ["oauth2server_client.client_id"],
            ondelete="CASCADE",
            name="fk_oauth2server_token_client_id_oauth2server_client",
        ),
        ForeignKeyConstraint(
            ["user_id"],
            ["accounts_user.id"],
            ondelete="CASCADE",
            name="fk_oauth2server_token_user_id_accounts_user",
        ),
        PrimaryKeyConstraint("id", name="pk_oauth2server_token"),
        Index("ix_oauth2server_token_access_token", "access_token", unique=True),
        Index("ix_oauth2server_token_client_id", "client_id"),
        Index("ix_oauth2server_token_refresh_token", "refresh_token", unique=True),
        Index("ix_oauth2server_token_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    token_type: Mapped[Optional[str]] = mapped_column(String(255))
    access_token: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    refresh_token: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    expires: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    _scopes: Mapped[Optional[str]] = mapped_column(Text)
    is_personal: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_internal: Mapped[Optional[bool]] = mapped_column(Boolean)

    client: Mapped["Oauth2serverClient"] = relationship(
        "Oauth2serverClient", back_populates="oauth2server_token"
    )
    user: Mapped[Optional["AccountsUser"]] = relationship(
        "AccountsUser", back_populates="oauth2server_token"
    )


class OauthclientRemotetoken(Base):
    __tablename__ = "oauthclient_remotetoken"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id_remote_account"],
            ["oauthclient_remoteaccount.id"],
            name="fk_oauthclient_remote_token_remote_account",
        ),
        PrimaryKeyConstraint(
            "id_remote_account", "token_type", name="pk_oauthclient_remotetoken"
        ),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    id_remote_account: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    access_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    secret: Mapped[str] = mapped_column(Text, nullable=False)

    oauthclient_remoteaccount: Mapped["OauthclientRemoteaccount"] = relationship(
        "OauthclientRemoteaccount", back_populates="oauthclient_remotetoken"
    )


t_records_buckets = Table(
    "records_buckets",
    Base.metadata,
    Column("record_id", Uuid, primary_key=True),
    Column("bucket_id", Uuid, primary_key=True),
    ForeignKeyConstraint(
        ["bucket_id"],
        ["files_bucket.id"],
        name="fk_records_buckets_bucket_id_files_bucket",
    ),
    ForeignKeyConstraint(
        ["record_id"],
        ["records_metadata.id"],
        name="fk_records_buckets_record_id_records_metadata",
    ),
    PrimaryKeyConstraint("record_id", "bucket_id", name="pk_records_buckets"),
)


class FilesMultipartobjectPart(Base):
    __tablename__ = "files_multipartobject_part"
    __table_args__ = (
        ForeignKeyConstraint(
            ["upload_id"],
            ["files_multipartobject.upload_id"],
            ondelete="RESTRICT",
            name="fk_files_multipartobject_part_upload_id_files_multipartobject",
        ),
        PrimaryKeyConstraint(
            "upload_id", "part_number", name="pk_files_multipartobject_part"
        ),
    )

    created: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    updated: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    upload_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    part_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(255))

    upload: Mapped["FilesMultipartobject"] = relationship(
        "FilesMultipartobject", back_populates="files_multipartobject_part"
    )


class FilesObjecttags(Base):
    __tablename__ = "files_objecttags"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id"],
            ["files_object.version_id"],
            ondelete="CASCADE",
            name="fk_files_objecttags_version_id_files_object",
        ),
        PrimaryKeyConstraint("version_id", "key", name="pk_files_objecttags"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    version: Mapped["FilesObject"] = relationship(
        "FilesObject", back_populates="files_objecttags"
    )
