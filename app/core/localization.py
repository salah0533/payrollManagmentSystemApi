from __future__ import annotations

from contextvars import ContextVar, Token
from enum import Enum
from typing import Any, Mapping


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "fr", "ar")

_current_language: ContextVar[str] = ContextVar("current_language", default=DEFAULT_LANGUAGE)


class LanguageCode(str, Enum):
    en = "en"
    fr = "fr"
    ar = "ar"


TRANSLATIONS: dict[str, dict[str, Any]] = {
    "en": {
        "auth": {
            "password_changed": "Password changed successfully",
            "logout_message": "Logout is stateless; discard the access and refresh tokens on the client.",
            "username_or_email_not_found": "Username or email was not found",
            "inactive_login": "Inactive users cannot log in",
            "password_incorrect": "Password is incorrect",
            "invalid_refresh_token": "Invalid refresh token",
            "inactive_refresh": "Inactive users cannot refresh tokens",
            "current_password_incorrect": "Current password is incorrect",
            "password_change_required": "Password change required before accessing this resource",
            "credentials_invalid": "Could not validate credentials",
            "inactive_access": "Inactive users cannot access this resource",
        },
        "labels": {
            "salary_type": {
                "monthly": "Monthly",
                "daily": "Daily",
                "hourly": "Hourly",
            },
            "vacation_status": {
                "pending": "Pending",
                "approved": "Approved",
                "rejected": "Rejected",
                "cancelled": "Cancelled",
                "canceled": "Cancelled",
            },
            "vacation_type": {
                "paid": "Paid vacation",
                "unpaid": "Unpaid vacation",
                "sick": "Sick leave",
                "emergency": "Emergency leave",
                "holiday": "Holiday",
                "yearly_vacation": "Yearly vacation",
                "vacation": "Vacation",
                "sick_leave": "Sick leave",
            },
            "attendance_status": {
                "present": "Present",
                "late": "Late",
                "absent": "Absent",
                "incomplete": "Incomplete",
                "weekly_off": "Weekly off",
                "holiday": "Holiday",
                "paid_vacation": "Paid vacation",
                "unpaid_vacation": "Unpaid vacation",
                "unpaid": "Unpaid",
                "sick_leave": "Sick leave",
                "manually_corrected": "Manually corrected",
            },
        },
        "common": {
            "yes": "Yes",
            "no": "No",
            "unknown_employee": "Employee #{{employee_id}}",
            "unknown_user": "User #{{user_id}}",
            "date_range": "{{start_date}} to {{end_date}}",
            "payroll_period_number": "period #{{period_id}}",
        },
        "errors": {
            "application_error": "Application error",
            "bad_request": "Bad request",
            "forbidden": "You do not have permission to perform this action",
            "unauthorized": "Authentication required",
            "not_found": "Requested resource was not found",
            "conflict": "Request conflicts with the current state of the resource",
            "validation_failed": "Validation failed",
            "database_error": "A database error occurred while processing the request",
            "internal_server_error": "An unexpected server error occurred",
            "integrity_duplicate": "A record with the same unique value already exists",
            "integrity_reference": "The request references a related record that does not exist",
            "integrity_generic": "Database constraint violation",
            "no_active_notification_recipients": "No active notification recipients were found",
            "role_code_required": "At least one role code is required",
            "at_least_one_role_required": "At least one role is required",
            "employee_role_requires_profile": "Employee role requires the user to be linked to an employee profile",
            "employee_already_linked": "This employee already has an active user account",
            "username_exists": "Username already exists",
            "email_exists": "Email already exists",
            "last_active_admin": "Cannot deactivate the last active admin",
            "last_active_admin_role": "Cannot remove the last active admin role",
            "inactive_employee_attendance": "Inactive employees cannot create attendance",
            "employee_on_approved_vacation": "Employee is on approved vacation",
            "duplicate_check_in": "Duplicate check-in is not allowed",
            "duplicate_break_start": "Duplicate break start is not allowed",
            "cannot_break_before_check_in": "Cannot start break before check-in",
            "duplicate_break_end": "Duplicate break end is not allowed",
            "cannot_end_break_before_start": "Cannot end break before break start",
            "break_end_before_break_start": "Break end cannot be before break start",
            "cannot_check_out_before_check_in": "Cannot check out before check-in",
            "duplicate_check_out": "Duplicate check-out is not allowed",
            "check_out_before_check_in": "Check-out cannot be before check-in",
            "invalid_attendance_event_type": "Invalid attendance event type",
            "start_before_end": "start_date must be before end_date",
            "weekly_off_only": "This date is not a weekly off day in the assigned work schedule",
            "weekly_off_cannot_be_absent": "Weekly off days cannot be changed to absent",
            "unsupported_smart_target_status": "Unsupported smart attendance target status",
            "attendance_correction_missing_fields": "Provide at least one attendance time field to correct",
            "set_check_in_first_break_start": "Set check-in before setting break start",
            "set_break_start_first_break_end": "Set break start before setting break end",
            "set_check_in_first_check_out": "Set check-in before setting check-out",
            "set_break_end_first_check_out": "Set break end before setting check-out",
            "check_in_before_break_start": "Check-in must be before break start",
            "check_in_before_check_out": "Check-in must be before check-out",
            "break_start_before_break_end": "Break start must be before break end",
            "break_start_before_check_out": "Break start must be before check-out",
            "break_end_before_check_out": "Break end must be before check-out",
            "approved_or_paid_payroll_recalc": "Approved or paid payroll cannot be recalculated",
            "resolve_high_severity_first": "Resolve high-severity discrepancies before approval",
            "resolve_high_severity_before_payment": "Resolve high-severity discrepancies before payment",
            "payment_amount_zero": "Payment amount cannot be zero",
            "payment_amount_negative": "Payment amount cannot be negative",
            "payment_amount_exceeds_balance": "Payment amount cannot exceed the remaining payroll balance",
            "locked_adjustments_immutable": "Approved, paid, or locked payroll adjustments cannot be changed",
            "settings_not_initialized": "Settings row does not exist",
            "legacy_attendance_write_disabled": "Legacy attendance write endpoints are disabled. Use AttendanceDay events or correction endpoints.",
            "legacy_attendance_delete_disabled": "Legacy attendance delete endpoints are disabled. Use /attendance/day/{employee_id}/{work_date}.",
            "vacation_overlap": "Vacation already exists in the requested range",
            "me_profile_missing": "This user is not linked to an employee profile",
            "notification_send_permission_missing": "Missing required permission(s): {{permissions}}",
            "access_other_employee_forbidden": "You are not allowed to access another employee's data",
            "missing_role": "You do not have the required role",
            "auto_attendance_enabled": "Auto attendance is enabled for this employee. Self-service attendance actions are disabled.",
            "resource_not_found_with_identifier": "{{resource_name}} with identifier '{{identifier}}' was not found",
            "resource_not_found": "{{resource_name}} not found",
            "invalid_month_format": "Invalid format. Use YYYY-MM",
        },
        "notifications": {
            "attendance_missing_checkout_title": "Missing check-out",
            "attendance_missing_checkout_message": "Your attendance for {{work_date}} is missing a check-out.",
            "attendance_missing_checkin_title": "Missing check-in",
            "attendance_missing_checkin_message": "Your attendance for {{work_date}} is missing a check-in.",
            "attendance_missing_break_start_title": "Missing break start",
            "attendance_missing_break_start_message": "Your attendance for {{work_date}} is missing a break start.",
            "attendance_missing_break_end_title": "Missing break end",
            "attendance_missing_break_end_message": "Your attendance for {{work_date}} is missing a break end.",
            "attendance_late_title": "Late attendance",
            "attendance_late_message": "Your check-in on {{work_date}} was marked as late.",
            "vacation_request_submitted_title": "Vacation request submitted",
            "vacation_request_submitted_message": "{{employee_name}} submitted a vacation request for {{period}}.",
            "vacation_approved_title": "Vacation approved",
            "vacation_approved_message": "Your vacation request for {{period}} was approved.",
            "vacation_rejected_title": "Vacation rejected",
            "vacation_rejected_message": "Your vacation request for {{period}} was rejected.",
            "vacation_cancelled_title": "Vacation cancelled",
            "vacation_cancelled_message": "Your vacation request for {{period}} was cancelled.",
            "account_created_title": "Account created",
            "account_created_message": "Your employee management account is ready to use.",
            "must_change_password_title": "Password change required",
            "must_change_password_message": "You must change your password before accessing the rest of the app.",
            "admin_forced_password_change_message": "An administrator requires you to change your password before continuing.",
            "password_changed_title": "Password changed",
            "password_changed_message": "Your password was changed successfully.",
            "password_reset_title": "Password reset",
            "password_reset_with_change_message": "Your password was reset. You must change it at your next login.",
            "password_reset_without_change_message": "Your password was reset by an administrator.",
            "payroll_draft_ready_title": "Payroll draft ready",
            "payroll_draft_ready_message": "Payroll draft for {{employee_name}} in period #{{period_id}} is ready.",
            "payroll_needs_review_title": "Payroll needs review",
            "payroll_needs_review_message": "Payroll for {{employee_name}} in period #{{period_id}} needs review.",
            "payroll_approved_title": "Payroll approved",
            "payroll_approved_message": "Your payroll for period #{{period_id}} was approved.",
            "payroll_paid_title": "Payroll payment recorded",
            "payroll_paid_message": "A payroll payment of {{payment_amount}} was recorded for period #{{period_id}}. Remaining balance: {{balance_amount}}.",
            "payroll_discrepancy_detected_title": "Payroll discrepancy detected",
            "payroll_discrepancy_detected_message": "{{description}}",
        },
        "validation": {
            "field_required": "This field is required",
            "invalid_value": "Invalid value",
            "target_user_or_role_required": "At least one target user or role is required",
        },
    },
    "fr": {
        "auth": {
            "password_changed": "Mot de passe modifie avec succes",
            "logout_message": "La deconnexion est sans etat ; supprimez les jetons d'acces et de rafraichissement cote client.",
            "username_or_email_not_found": "Nom d'utilisateur ou e-mail introuvable",
            "inactive_login": "Les utilisateurs inactifs ne peuvent pas se connecter",
            "password_incorrect": "Le mot de passe est incorrect",
            "invalid_refresh_token": "Jeton de rafraichissement invalide",
            "inactive_refresh": "Les utilisateurs inactifs ne peuvent pas rafraichir les jetons",
            "current_password_incorrect": "Le mot de passe actuel est incorrect",
            "password_change_required": "Le changement de mot de passe est requis avant d'acceder a cette ressource",
            "credentials_invalid": "Impossible de valider les identifiants",
            "inactive_access": "Les utilisateurs inactifs ne peuvent pas acceder a cette ressource",
        },
        "labels": {
            "salary_type": {
                "monthly": "Mensuel",
                "daily": "Journalier",
                "hourly": "Horaire",
            },
            "vacation_status": {
                "pending": "En attente",
                "approved": "Approuve",
                "rejected": "Refuse",
                "cancelled": "Annule",
                "canceled": "Annule",
            },
            "vacation_type": {
                "paid": "Conge paye",
                "unpaid": "Conge non paye",
                "sick": "Conge maladie",
                "emergency": "Conge d'urgence",
                "holiday": "Jour ferie",
                "yearly_vacation": "Conge annuel",
                "vacation": "Conge",
                "sick_leave": "Conge maladie",
            },
            "attendance_status": {
                "present": "Present",
                "late": "Retard",
                "absent": "Absent",
                "incomplete": "Incomplet",
                "weekly_off": "Repos hebdomadaire",
                "holiday": "Jour ferie",
                "paid_vacation": "Conge paye",
                "unpaid_vacation": "Conge non paye",
                "unpaid": "Non paye",
                "sick_leave": "Conge maladie",
                "manually_corrected": "Corrige manuellement",
            },
        },
        "common": {
            "yes": "Oui",
            "no": "Non",
            "unknown_employee": "Employe n°{{employee_id}}",
            "unknown_user": "Utilisateur n°{{user_id}}",
            "date_range": "du {{start_date}} au {{end_date}}",
            "payroll_period_number": "la periode n°{{period_id}}",
        },
        "errors": {
            "application_error": "Erreur de l'application",
            "bad_request": "Requete invalide",
            "forbidden": "Vous n'etes pas autorise a effectuer cette action",
            "unauthorized": "Authentification requise",
            "not_found": "La ressource demandee est introuvable",
            "conflict": "La requete entre en conflit avec l'etat actuel de la ressource",
            "validation_failed": "La validation a echoue",
            "database_error": "Une erreur de base de donnees s'est produite pendant le traitement de la requete",
            "internal_server_error": "Une erreur serveur inattendue s'est produite",
            "integrity_duplicate": "Un enregistrement avec la meme valeur unique existe deja",
            "integrity_reference": "La requete reference un enregistrement lie qui n'existe pas",
            "integrity_generic": "Violation d'une contrainte de base de donnees",
            "no_active_notification_recipients": "Aucun destinataire actif n'a ete trouve pour la notification",
            "role_code_required": "Au moins un code de role est requis",
            "at_least_one_role_required": "Au moins un role est requis",
            "employee_role_requires_profile": "Le role employe exige un lien avec une fiche employe",
            "employee_already_linked": "Cet employe possede deja un compte utilisateur actif",
            "username_exists": "Le nom d'utilisateur existe deja",
            "email_exists": "L'e-mail existe deja",
            "last_active_admin": "Impossible de desactiver le dernier administrateur actif",
            "last_active_admin_role": "Impossible de retirer le dernier role administrateur actif",
            "inactive_employee_attendance": "Les employes inactifs ne peuvent pas creer de pointage",
            "employee_on_approved_vacation": "L'employe est en conge approuve",
            "duplicate_check_in": "Le pointage d'entree en double n'est pas autorise",
            "duplicate_break_start": "Le debut de pause en double n'est pas autorise",
            "cannot_break_before_check_in": "Impossible de commencer la pause avant l'entree",
            "duplicate_break_end": "La fin de pause en double n'est pas autorisee",
            "cannot_end_break_before_start": "Impossible de terminer la pause avant son debut",
            "break_end_before_break_start": "La fin de pause ne peut pas preceder le debut de pause",
            "cannot_check_out_before_check_in": "Impossible de sortir avant l'entree",
            "duplicate_check_out": "Le pointage de sortie en double n'est pas autorise",
            "check_out_before_check_in": "La sortie ne peut pas preceder l'entree",
            "invalid_attendance_event_type": "Type d'evenement de presence invalide",
            "start_before_end": "start_date doit etre anterieure a end_date",
            "weekly_off_only": "Cette date n'est pas un jour de repos hebdomadaire dans l'horaire assigne",
            "weekly_off_cannot_be_absent": "Les jours de repos hebdomadaire ne peuvent pas etre changes en absence",
            "unsupported_smart_target_status": "Statut cible intelligent non pris en charge",
            "attendance_correction_missing_fields": "Fournissez au moins un champ horaire a corriger",
            "set_check_in_first_break_start": "Definissez l'entree avant le debut de pause",
            "set_break_start_first_break_end": "Definissez le debut de pause avant la fin de pause",
            "set_check_in_first_check_out": "Definissez l'entree avant la sortie",
            "set_break_end_first_check_out": "Definissez la fin de pause avant la sortie",
            "check_in_before_break_start": "L'entree doit preceder le debut de pause",
            "check_in_before_check_out": "L'entree doit preceder la sortie",
            "break_start_before_break_end": "Le debut de pause doit preceder la fin de pause",
            "break_start_before_check_out": "Le debut de pause doit preceder la sortie",
            "break_end_before_check_out": "La fin de pause doit preceder la sortie",
            "approved_or_paid_payroll_recalc": "Une paie approuvee ou payee ne peut pas etre recalculee",
            "resolve_high_severity_first": "Resolvez les anomalies de gravite elevee avant l'approbation",
            "resolve_high_severity_before_payment": "Resolvez les anomalies de gravite elevee avant le paiement",
            "payment_amount_zero": "Le montant du paiement ne peut pas etre nul",
            "payment_amount_negative": "Le montant du paiement ne peut pas etre negatif",
            "payment_amount_exceeds_balance": "Le montant du paiement ne peut pas depasser le solde restant",
            "locked_adjustments_immutable": "Les ajustements de paie approuves, payes ou verrouilles ne peuvent pas etre modifies",
            "settings_not_initialized": "La ligne de parametres n'existe pas",
            "legacy_attendance_write_disabled": "Les anciens points d'ecriture de presence sont desactives. Utilisez les evenements AttendanceDay ou les points de correction.",
            "legacy_attendance_delete_disabled": "Les anciens points de suppression de presence sont desactives. Utilisez /attendance/day/{employee_id}/{work_date}.",
            "vacation_overlap": "Un conge existe deja dans la periode demandee",
            "me_profile_missing": "Cet utilisateur n'est pas lie a un profil employe",
            "notification_send_permission_missing": "Autorisation(s) requise(s) manquante(s) : {{permissions}}",
            "access_other_employee_forbidden": "Vous n'etes pas autorise a acceder aux donnees d'un autre employe",
            "missing_role": "Vous n'avez pas le role requis",
            "auto_attendance_enabled": "La presence automatique est activee pour cet employe. Les actions de presence en libre-service sont desactivees.",
            "resource_not_found_with_identifier": "{{resource_name}} avec l'identifiant '{{identifier}}' est introuvable",
            "resource_not_found": "{{resource_name}} introuvable",
            "invalid_month_format": "Format invalide. Utilisez AAAA-MM",
        },
        "notifications": {
            "attendance_missing_checkout_title": "Sortie manquante",
            "attendance_missing_checkout_message": "Votre presence du {{work_date}} ne contient pas de sortie.",
            "attendance_missing_checkin_title": "Entree manquante",
            "attendance_missing_checkin_message": "Votre presence du {{work_date}} ne contient pas d'entree.",
            "attendance_missing_break_start_title": "Début de pause manquant",
            "attendance_missing_break_start_message": "Votre présence du {{work_date}} ne contient pas de début de pause.",
            "attendance_missing_break_end_title": "Fin de pause manquante",
            "attendance_missing_break_end_message": "Votre présence du {{work_date}} ne contient pas de fin de pause.",
            "attendance_late_title": "Retard constate",
            "attendance_late_message": "Votre entree du {{work_date}} a ete marquee en retard.",
            "vacation_request_submitted_title": "Demande de conge envoyee",
            "vacation_request_submitted_message": "{{employee_name}} a soumis une demande de conge pour {{period}}.",
            "vacation_approved_title": "Conge approuve",
            "vacation_approved_message": "Votre demande de conge pour {{period}} a ete approuvee.",
            "vacation_rejected_title": "Conge refuse",
            "vacation_rejected_message": "Votre demande de conge pour {{period}} a ete refusee.",
            "vacation_cancelled_title": "Conge annule",
            "vacation_cancelled_message": "Votre demande de conge pour {{period}} a ete annulee.",
            "account_created_title": "Compte cree",
            "account_created_message": "Votre compte de gestion du personnel est pret a etre utilise.",
            "must_change_password_title": "Changement de mot de passe requis",
            "must_change_password_message": "Vous devez changer votre mot de passe avant d'acceder au reste de l'application.",
            "admin_forced_password_change_message": "Un administrateur vous oblige a changer votre mot de passe avant de continuer.",
            "password_changed_title": "Mot de passe modifie",
            "password_changed_message": "Votre mot de passe a ete modifie avec succes.",
            "password_reset_title": "Mot de passe reinitialise",
            "password_reset_with_change_message": "Votre mot de passe a ete reinitialise. Vous devrez le changer lors de votre prochaine connexion.",
            "password_reset_without_change_message": "Votre mot de passe a ete reinitialise par un administrateur.",
            "payroll_draft_ready_title": "Brouillon de paie pret",
            "payroll_draft_ready_message": "Le brouillon de paie pour {{employee_name}} dans la periode n°{{period_id}} est pret.",
            "payroll_needs_review_title": "La paie doit etre verifiee",
            "payroll_needs_review_message": "La paie de {{employee_name}} dans la periode n°{{period_id}} doit etre verifiee.",
            "payroll_approved_title": "Paie approuvee",
            "payroll_approved_message": "Votre paie pour la periode n°{{period_id}} a ete approuvee.",
            "payroll_paid_title": "Paiement de paie enregistre",
            "payroll_paid_message": "Un paiement de paie de {{payment_amount}} a ete enregistre pour la periode n°{{period_id}}. Solde restant : {{balance_amount}}.",
            "payroll_discrepancy_detected_title": "Anomalie de paie detectee",
            "payroll_discrepancy_detected_message": "{{description}}",
        },
        "validation": {
            "field_required": "Ce champ est obligatoire",
            "invalid_value": "Valeur invalide",
            "target_user_or_role_required": "Au moins un utilisateur cible ou un role est requis",
        },
    },
    "ar": {
        "auth": {
            "password_changed": "تم تغيير كلمة المرور بنجاح",
            "logout_message": "تسجيل الخروج عديم الحالة؛ تخلص من رمزي الوصول والتحديث من جهة العميل.",
            "username_or_email_not_found": "اسم المستخدم أو البريد الإلكتروني غير موجود",
            "inactive_login": "لا يمكن للمستخدمين غير النشطين تسجيل الدخول",
            "password_incorrect": "كلمة المرور غير صحيحة",
            "invalid_refresh_token": "رمز التحديث غير صالح",
            "inactive_refresh": "لا يمكن للمستخدمين غير النشطين تحديث الرموز",
            "current_password_incorrect": "كلمة المرور الحالية غير صحيحة",
            "password_change_required": "يجب تغيير كلمة المرور قبل الوصول إلى هذا المورد",
            "credentials_invalid": "تعذر التحقق من بيانات الاعتماد",
            "inactive_access": "لا يمكن للمستخدمين غير النشطين الوصول إلى هذا المورد",
        },
        "labels": {
            "salary_type": {
                "monthly": "شهري",
                "daily": "يومي",
                "hourly": "بالساعة",
            },
            "vacation_status": {
                "pending": "قيد الانتظار",
                "approved": "معتمد",
                "rejected": "مرفوض",
                "cancelled": "ملغى",
                "canceled": "ملغى",
            },
            "vacation_type": {
                "paid": "إجازة مدفوعة",
                "unpaid": "إجازة غير مدفوعة",
                "sick": "إجازة مرضية",
                "emergency": "إجازة طارئة",
                "holiday": "عطلة",
                "yearly_vacation": "إجازة سنوية",
                "vacation": "إجازة",
                "sick_leave": "إجازة مرضية",
            },
            "attendance_status": {
                "present": "حاضر",
                "late": "متأخر",
                "absent": "غائب",
                "incomplete": "غير مكتمل",
                "weekly_off": "عطلة أسبوعية",
                "holiday": "عطلة",
                "paid_vacation": "إجازة مدفوعة",
                "unpaid_vacation": "إجازة غير مدفوعة",
                "unpaid": "غير مدفوع",
                "sick_leave": "إجازة مرضية",
                "manually_corrected": "مصَحح يدوياً",
            },
        },
        "common": {
            "yes": "نعم",
            "no": "لا",
            "unknown_employee": "الموظف رقم {{employee_id}}",
            "unknown_user": "المستخدم رقم {{user_id}}",
            "date_range": "{{start_date}} إلى {{end_date}}",
            "payroll_period_number": "الفترة رقم {{period_id}}",
        },
        "errors": {
            "application_error": "خطأ في التطبيق",
            "bad_request": "الطلب غير صالح",
            "forbidden": "ليست لديك صلاحية لتنفيذ هذا الإجراء",
            "unauthorized": "المصادقة مطلوبة",
            "not_found": "المورد المطلوب غير موجود",
            "conflict": "الطلب يتعارض مع الحالة الحالية للمورد",
            "validation_failed": "فشل التحقق من صحة البيانات",
            "database_error": "حدث خطأ في قاعدة البيانات أثناء معالجة الطلب",
            "internal_server_error": "حدث خطأ خادم غير متوقع",
            "integrity_duplicate": "يوجد سجل آخر بالقيمة الفريدة نفسها",
            "integrity_reference": "يشير الطلب إلى سجل مرتبط غير موجود",
            "integrity_generic": "انتهاك لقيد في قاعدة البيانات",
            "no_active_notification_recipients": "لم يتم العثور على مستلمين نشطين للإشعار",
            "role_code_required": "مطلوب رمز دور واحد على الأقل",
            "at_least_one_role_required": "مطلوب دور واحد على الأقل",
            "employee_role_requires_profile": "يتطلب دور الموظف ربط المستخدم بملف موظف",
            "employee_already_linked": "هذا الموظف لديه بالفعل حساب مستخدم نشط",
            "username_exists": "اسم المستخدم موجود بالفعل",
            "email_exists": "البريد الإلكتروني موجود بالفعل",
            "last_active_admin": "لا يمكن تعطيل آخر مسؤول نشط",
            "last_active_admin_role": "لا يمكن إزالة آخر دور مسؤول نشط",
            "inactive_employee_attendance": "لا يمكن للموظفين غير النشطين إنشاء حضور",
            "employee_on_approved_vacation": "الموظف في إجازة معتمدة",
            "duplicate_check_in": "لا يُسمح بتسجيل دخول مكرر",
            "duplicate_break_start": "لا يُسمح ببدء استراحة مكرر",
            "cannot_break_before_check_in": "لا يمكن بدء الاستراحة قبل تسجيل الدخول",
            "duplicate_break_end": "لا يُسمح بإنهاء استراحة مكرر",
            "cannot_end_break_before_start": "لا يمكن إنهاء الاستراحة قبل بدئها",
            "break_end_before_break_start": "لا يمكن أن يكون إنهاء الاستراحة قبل بدئها",
            "cannot_check_out_before_check_in": "لا يمكن تسجيل الخروج قبل تسجيل الدخول",
            "duplicate_check_out": "لا يُسمح بتسجيل خروج مكرر",
            "check_out_before_check_in": "لا يمكن أن يكون تسجيل الخروج قبل تسجيل الدخول",
            "invalid_attendance_event_type": "نوع حدث الحضور غير صالح",
            "start_before_end": "يجب أن يكون start_date قبل end_date",
            "weekly_off_only": "هذا التاريخ ليس يوم عطلة أسبوعية في جدول العمل المعيّن",
            "weekly_off_cannot_be_absent": "لا يمكن تحويل أيام العطلة الأسبوعية إلى غياب",
            "unsupported_smart_target_status": "حالة الحضور الذكية المستهدفة غير مدعومة",
            "attendance_correction_missing_fields": "قدّم حقلاً زمنياً واحداً على الأقل لتصحيحه",
            "set_check_in_first_break_start": "اضبط تسجيل الدخول قبل ضبط بدء الاستراحة",
            "set_break_start_first_break_end": "اضبط بدء الاستراحة قبل ضبط نهايتها",
            "set_check_in_first_check_out": "اضبط تسجيل الدخول قبل ضبط تسجيل الخروج",
            "set_break_end_first_check_out": "اضبط نهاية الاستراحة قبل ضبط تسجيل الخروج",
            "check_in_before_break_start": "يجب أن يكون تسجيل الدخول قبل بدء الاستراحة",
            "check_in_before_check_out": "يجب أن يكون تسجيل الدخول قبل تسجيل الخروج",
            "break_start_before_break_end": "يجب أن يكون بدء الاستراحة قبل نهايتها",
            "break_start_before_check_out": "يجب أن يكون بدء الاستراحة قبل تسجيل الخروج",
            "break_end_before_check_out": "يجب أن تكون نهاية الاستراحة قبل تسجيل الخروج",
            "approved_or_paid_payroll_recalc": "لا يمكن إعادة احتساب كشف رواتب معتمد أو مدفوع",
            "resolve_high_severity_first": "عالج الفروقات عالية الخطورة قبل الاعتماد",
            "resolve_high_severity_before_payment": "عالج الفروقات عالية الخطورة قبل الدفع",
            "payment_amount_zero": "لا يمكن أن يكون مبلغ الدفع صفراً",
            "payment_amount_negative": "لا يمكن أن يكون مبلغ الدفع سالباً",
            "payment_amount_exceeds_balance": "لا يمكن أن يتجاوز مبلغ الدفع الرصيد المتبقي",
            "locked_adjustments_immutable": "لا يمكن تغيير تعديلات الرواتب المعتمدة أو المدفوعة أو المقفلة",
            "settings_not_initialized": "صف الإعدادات غير موجود",
            "legacy_attendance_write_disabled": "تم تعطيل نقاط كتابة الحضور القديمة. استخدم أحداث AttendanceDay أو نقاط التصحيح.",
            "legacy_attendance_delete_disabled": "تم تعطيل نقاط حذف الحضور القديمة. استخدم ‎/attendance/day/{employee_id}/{work_date}.",
            "vacation_overlap": "توجد إجازة بالفعل ضمن النطاق المطلوب",
            "me_profile_missing": "هذا المستخدم غير مرتبط بملف موظف",
            "notification_send_permission_missing": "أذونات مطلوبة مفقودة: {{permissions}}",
            "access_other_employee_forbidden": "غير مسموح لك بالوصول إلى بيانات موظف آخر",
            "missing_role": "ليس لديك الدور المطلوب",
            "auto_attendance_enabled": "تم تفعيل الحضور التلقائي لهذا الموظف. تم تعطيل إجراءات الحضور الذاتية.",
            "resource_not_found_with_identifier": "تعذر العثور على {{resource_name}} بالمعرّف '{{identifier}}'",
            "resource_not_found": "تعذر العثور على {{resource_name}}",
            "invalid_month_format": "تنسيق غير صالح. استخدم YYYY-MM",
        },
        "notifications": {
            "attendance_missing_checkout_title": "تسجيل الخروج مفقود",
            "attendance_missing_checkout_message": "سجل حضورك بتاريخ {{work_date}} يفتقد تسجيل الخروج.",
            "attendance_missing_checkin_title": "تسجيل الدخول مفقود",
            "attendance_missing_checkin_message": "سجل حضورك بتاريخ {{work_date}} يفتقد تسجيل الدخول.",
            "attendance_missing_break_start_title": "بدء الاستراحة مفقود",
            "attendance_missing_break_start_message": "سجل حضورك بتاريخ {{work_date}} يفتقد بدء الاستراحة.",
            "attendance_missing_break_end_title": "نهاية الاستراحة مفقودة",
            "attendance_missing_break_end_message": "سجل حضورك بتاريخ {{work_date}} يفتقد نهاية الاستراحة.",
            "attendance_late_title": "حضور متأخر",
            "attendance_late_message": "تم تصنيف تسجيل دخولك في {{work_date}} كمتأخر.",
            "vacation_request_submitted_title": "تم إرسال طلب الإجازة",
            "vacation_request_submitted_message": "قدّم {{employee_name}} طلب إجازة للفترة {{period}}.",
            "vacation_approved_title": "تمت الموافقة على الإجازة",
            "vacation_approved_message": "تمت الموافقة على طلب إجازتك للفترة {{period}}.",
            "vacation_rejected_title": "تم رفض الإجازة",
            "vacation_rejected_message": "تم رفض طلب إجازتك للفترة {{period}}.",
            "vacation_cancelled_title": "تم إلغاء الإجازة",
            "vacation_cancelled_message": "تم إلغاء طلب إجازتك للفترة {{period}}.",
            "account_created_title": "تم إنشاء الحساب",
            "account_created_message": "أصبح حساب إدارة الموظفين الخاص بك جاهزاً للاستخدام.",
            "must_change_password_title": "يجب تغيير كلمة المرور",
            "must_change_password_message": "يجب عليك تغيير كلمة المرور قبل الوصول إلى بقية التطبيق.",
            "admin_forced_password_change_message": "يتطلب المسؤول منك تغيير كلمة المرور قبل المتابعة.",
            "password_changed_title": "تم تغيير كلمة المرور",
            "password_changed_message": "تم تغيير كلمة المرور الخاصة بك بنجاح.",
            "password_reset_title": "إعادة تعيين كلمة المرور",
            "password_reset_with_change_message": "تمت إعادة تعيين كلمة المرور الخاصة بك. يجب تغييرها عند تسجيل الدخول التالي.",
            "password_reset_without_change_message": "أعاد أحد المسؤولين تعيين كلمة المرور الخاصة بك.",
            "payroll_draft_ready_title": "مسودة الرواتب جاهزة",
            "payroll_draft_ready_message": "مسودة رواتب {{employee_name}} للفترة رقم {{period_id}} جاهزة.",
            "payroll_needs_review_title": "الرواتب تحتاج إلى مراجعة",
            "payroll_needs_review_message": "رواتب {{employee_name}} للفترة رقم {{period_id}} تحتاج إلى مراجعة.",
            "payroll_approved_title": "تم اعتماد الرواتب",
            "payroll_approved_message": "تم اعتماد كشف رواتبك للفترة رقم {{period_id}}.",
            "payroll_paid_title": "تم تسجيل دفعة الرواتب",
            "payroll_paid_message": "تم تسجيل دفعة رواتب بقيمة {{payment_amount}} للفترة رقم {{period_id}}. الرصيد المتبقي: {{balance_amount}}.",
            "payroll_discrepancy_detected_title": "تم اكتشاف فرق في الرواتب",
            "payroll_discrepancy_detected_message": "{{description}}",
        },
        "validation": {
            "field_required": "هذا الحقل مطلوب",
            "invalid_value": "قيمة غير صالحة",
            "target_user_or_role_required": "مطلوب مستخدم مستهدف واحد على الأقل أو دور واحد على الأقل",
        },
    },
}

TRANSLATIONS["fr"]["auth"].update(
    {
        "password_changed": "Mot de passe modifié avec succès",
        "logout_message": "La déconnexion est sans état ; supprimez les jetons d'accès et de rafraîchissement côté client.",
        "username_or_email_not_found": "Nom d'utilisateur ou e-mail introuvable",
        "inactive_login": "Les utilisateurs inactifs ne peuvent pas se connecter",
        "password_incorrect": "Le mot de passe est incorrect",
        "invalid_refresh_token": "Jeton de rafraîchissement invalide",
        "inactive_refresh": "Les utilisateurs inactifs ne peuvent pas rafraîchir les jetons",
        "current_password_incorrect": "Le mot de passe actuel est incorrect",
        "password_change_required": "Le changement de mot de passe est requis avant d'accéder à cette ressource",
        "credentials_invalid": "Impossible de valider les identifiants",
        "inactive_access": "Les utilisateurs inactifs ne peuvent pas accéder à cette ressource",
    }
)
TRANSLATIONS["fr"]["common"].update(
    {
        "yes": "Oui",
        "no": "Non",
        "unknown_employee": "Employé n°{{employee_id}}",
        "unknown_user": "Utilisateur n°{{user_id}}",
        "date_range": "du {{start_date}} au {{end_date}}",
        "payroll_period_number": "la période n°{{period_id}}",
    }
)
TRANSLATIONS["fr"]["errors"].update(
    {
        "application_error": "Erreur de l'application",
        "bad_request": "Requête invalide",
        "forbidden": "Vous n'êtes pas autorisé à effectuer cette action",
        "unauthorized": "Authentification requise",
        "not_found": "La ressource demandée est introuvable",
        "conflict": "La requête entre en conflit avec l'état actuel de la ressource",
        "validation_failed": "La validation a échoué",
        "database_error": "Une erreur de base de données s'est produite pendant le traitement de la requête",
        "internal_server_error": "Une erreur serveur inattendue s'est produite",
        "no_active_notification_recipients": "Aucun destinataire actif n'a été trouvé pour la notification",
        "role_code_required": "Au moins un code de rôle est requis",
        "at_least_one_role_required": "Au moins un rôle est requis",
        "employee_role_requires_profile": "Le rôle employé exige un lien avec une fiche employé",
        "employee_already_linked": "Cet employé possède déjà un compte utilisateur actif",
        "username_exists": "Le nom d'utilisateur existe déjà",
        "email_exists": "L'e-mail existe déjà",
        "last_active_admin": "Impossible de désactiver le dernier administrateur actif",
        "last_active_admin_role": "Impossible de retirer le dernier rôle administrateur actif",
        "vacation_overlap": "Un congé existe déjà dans la période demandée",
        "me_profile_missing": "Cet utilisateur n'est pas lié à un profil employé",
        "missing_role": "Vous n'avez pas le rôle requis",
        "auto_attendance_enabled": "La présence automatique est activée pour cet employé. Les actions de présence en libre-service sont désactivées.",
        "resource_not_found_with_identifier": "{{resource_name}} avec l'identifiant '{{identifier}}' est introuvable",
        "resource_not_found": "{{resource_name}} introuvable",
        "invalid_month_format": "Format invalide. Utilisez YYYY-MM",
    }
)
TRANSLATIONS["fr"]["notifications"].update(
    {
        "attendance_missing_checkout_title": "Sortie manquante",
        "attendance_missing_checkout_message": "Votre présence du {{work_date}} ne contient pas de sortie.",
        "attendance_missing_checkin_title": "Entrée manquante",
        "attendance_missing_checkin_message": "Votre présence du {{work_date}} ne contient pas d'entrée.",
        "attendance_missing_break_start_title": "Début de pause manquant",
        "attendance_missing_break_start_message": "Votre présence du {{work_date}} ne contient pas de début de pause.",
        "attendance_missing_break_end_title": "Fin de pause manquante",
        "attendance_missing_break_end_message": "Votre présence du {{work_date}} ne contient pas de fin de pause.",
        "attendance_late_title": "Présence en retard",
        "attendance_late_message": "Votre entrée du {{work_date}} a été marquée en retard.",
        "vacation_request_submitted_title": "Demande de congé envoyée",
        "vacation_request_submitted_message": "{{employee_name}} a envoyé une demande de congé pour {{period}}.",
        "vacation_approved_title": "Congé approuvé",
        "vacation_approved_message": "Votre demande de congé pour {{period}} a été approuvée.",
        "vacation_rejected_title": "Congé refusé",
        "vacation_rejected_message": "Votre demande de congé pour {{period}} a été refusée.",
        "vacation_cancelled_title": "Congé annulé",
        "vacation_cancelled_message": "Votre demande de congé pour {{period}} a été annulée.",
        "account_created_title": "Compte créé",
        "account_created_message": "Votre compte de gestion des employés est prêt à être utilisé.",
        "must_change_password_title": "Changement de mot de passe requis",
        "must_change_password_message": "Vous devez changer votre mot de passe avant d'accéder au reste de l'application.",
        "admin_forced_password_change_message": "Un administrateur exige que vous changiez votre mot de passe avant de continuer.",
        "password_changed_title": "Mot de passe modifié",
        "password_changed_message": "Votre mot de passe a été modifié avec succès.",
        "password_reset_title": "Mot de passe réinitialisé",
        "password_reset_with_change_message": "Votre mot de passe a été réinitialisé. Vous devrez le changer lors de votre prochaine connexion.",
        "password_reset_without_change_message": "Votre mot de passe a été réinitialisé par un administrateur.",
        "payroll_draft_ready_title": "Brouillon de paie prêt",
        "payroll_draft_ready_message": "Le brouillon de paie de {{employee_name}} pour la période n°{{period_id}} est prêt.",
        "payroll_needs_review_title": "Paie à revoir",
        "payroll_needs_review_message": "La paie de {{employee_name}} pour la période n°{{period_id}} nécessite une révision.",
        "payroll_approved_title": "Paie approuvée",
        "payroll_approved_message": "Votre paie pour la période n°{{period_id}} a été approuvée.",
        "payroll_paid_title": "Paiement de paie enregistré",
        "payroll_paid_message": "Un paiement de {{payment_amount}} a été enregistré pour la période n°{{period_id}}. Solde restant : {{balance_amount}}.",
        "payroll_discrepancy_detected_title": "Écart de paie détecté",
        "payroll_discrepancy_detected_message": "{{description}}",
    }
)

TRANSLATIONS["ar"]["auth"].update(
    {
        "password_changed": "تم تغيير كلمة المرور بنجاح",
        "logout_message": "تسجيل الخروج عديم الحالة؛ تخلّص من رموز الوصول والتحديث من جهة العميل.",
        "username_or_email_not_found": "اسم المستخدم أو البريد الإلكتروني غير موجود",
        "inactive_login": "لا يمكن للمستخدمين غير النشطين تسجيل الدخول",
        "password_incorrect": "كلمة المرور غير صحيحة",
        "invalid_refresh_token": "رمز التحديث غير صالح",
        "inactive_refresh": "لا يمكن للمستخدمين غير النشطين تحديث الرموز",
        "current_password_incorrect": "كلمة المرور الحالية غير صحيحة",
        "password_change_required": "يجب تغيير كلمة المرور قبل الوصول إلى هذا المورد",
        "credentials_invalid": "تعذر التحقق من بيانات الاعتماد",
        "inactive_access": "لا يمكن للمستخدمين غير النشطين الوصول إلى هذا المورد",
    }
)
TRANSLATIONS["ar"]["common"].update(
    {
        "yes": "نعم",
        "no": "لا",
        "unknown_employee": "الموظف رقم {{employee_id}}",
        "unknown_user": "المستخدم رقم {{user_id}}",
        "date_range": "{{start_date}} إلى {{end_date}}",
        "payroll_period_number": "الفترة رقم {{period_id}}",
    }
)
TRANSLATIONS["ar"]["errors"].update(
    {
        "application_error": "خطأ في التطبيق",
        "bad_request": "الطلب غير صالح",
        "forbidden": "ليست لديك صلاحية لتنفيذ هذا الإجراء",
        "unauthorized": "المصادقة مطلوبة",
        "not_found": "المورد المطلوب غير موجود",
        "conflict": "الطلب يتعارض مع الحالة الحالية للمورد",
        "validation_failed": "فشل التحقق من صحة البيانات",
        "database_error": "حدث خطأ في قاعدة البيانات أثناء معالجة الطلب",
        "internal_server_error": "حدث خطأ خادم غير متوقع",
        "no_active_notification_recipients": "لم يتم العثور على مستلمين نشطين للإشعار",
        "role_code_required": "مطلوب رمز دور واحد على الأقل",
        "at_least_one_role_required": "مطلوب دور واحد على الأقل",
        "employee_role_requires_profile": "يتطلب دور الموظف ربط المستخدم بملف موظف",
        "employee_already_linked": "هذا الموظف لديه بالفعل حساب مستخدم نشط",
        "username_exists": "اسم المستخدم موجود بالفعل",
        "email_exists": "البريد الإلكتروني موجود بالفعل",
        "last_active_admin": "لا يمكن تعطيل آخر مسؤول نشط",
        "last_active_admin_role": "لا يمكن إزالة آخر دور مسؤول نشط",
        "vacation_overlap": "توجد إجازة بالفعل ضمن النطاق المطلوب",
        "me_profile_missing": "هذا المستخدم غير مرتبط بملف موظف",
        "missing_role": "ليس لديك الدور المطلوب",
        "auto_attendance_enabled": "تم تفعيل الحضور التلقائي لهذا الموظف. تم تعطيل إجراءات الحضور الذاتية.",
        "resource_not_found_with_identifier": "تعذر العثور على {{resource_name}} بالمعرّف '{{identifier}}'",
        "resource_not_found": "تعذر العثور على {{resource_name}}",
        "invalid_month_format": "تنسيق غير صالح. استخدم YYYY-MM",
    }
)
TRANSLATIONS["ar"]["notifications"].update(
    {
        "attendance_missing_checkout_title": "تسجيل الخروج مفقود",
        "attendance_missing_checkout_message": "سجل حضورك بتاريخ {{work_date}} يفتقد تسجيل الخروج.",
        "attendance_missing_checkin_title": "تسجيل الدخول مفقود",
        "attendance_missing_checkin_message": "سجل حضورك بتاريخ {{work_date}} يفتقد تسجيل الدخول.",
        "attendance_missing_break_start_title": "بدء الاستراحة مفقود",
        "attendance_missing_break_start_message": "سجل حضورك بتاريخ {{work_date}} يفتقد بدء الاستراحة.",
        "attendance_missing_break_end_title": "نهاية الاستراحة مفقودة",
        "attendance_missing_break_end_message": "سجل حضورك بتاريخ {{work_date}} يفتقد نهاية الاستراحة.",
        "attendance_late_title": "حضور متأخر",
        "attendance_late_message": "تم تصنيف تسجيل دخولك في {{work_date}} كمتأخر.",
        "vacation_request_submitted_title": "تم إرسال طلب الإجازة",
        "vacation_request_submitted_message": "قدّم {{employee_name}} طلب إجازة للفترة {{period}}.",
        "vacation_approved_title": "تمت الموافقة على الإجازة",
        "vacation_approved_message": "تمت الموافقة على طلب إجازتك للفترة {{period}}.",
        "vacation_rejected_title": "تم رفض الإجازة",
        "vacation_rejected_message": "تم رفض طلب إجازتك للفترة {{period}}.",
        "vacation_cancelled_title": "تم إلغاء الإجازة",
        "vacation_cancelled_message": "تم إلغاء طلب إجازتك للفترة {{period}}.",
        "account_created_title": "تم إنشاء الحساب",
        "account_created_message": "أصبح حساب إدارة الموظفين الخاص بك جاهزًا للاستخدام.",
        "must_change_password_title": "يجب تغيير كلمة المرور",
        "must_change_password_message": "يجب عليك تغيير كلمة المرور قبل الوصول إلى بقية التطبيق.",
        "admin_forced_password_change_message": "يتطلب المسؤول منك تغيير كلمة المرور قبل المتابعة.",
        "password_changed_title": "تم تغيير كلمة المرور",
        "password_changed_message": "تم تغيير كلمة المرور الخاصة بك بنجاح.",
        "password_reset_title": "إعادة تعيين كلمة المرور",
        "password_reset_with_change_message": "تمت إعادة تعيين كلمة المرور الخاصة بك. يجب تغييرها عند تسجيل الدخول التالي.",
        "password_reset_without_change_message": "أعاد أحد المسؤولين تعيين كلمة المرور الخاصة بك.",
        "payroll_draft_ready_title": "مسودة الرواتب جاهزة",
        "payroll_draft_ready_message": "مسودة رواتب {{employee_name}} للفترة رقم {{period_id}} جاهزة.",
        "payroll_needs_review_title": "الرواتب تحتاج إلى مراجعة",
        "payroll_needs_review_message": "رواتب {{employee_name}} للفترة رقم {{period_id}} تحتاج إلى مراجعة.",
        "payroll_approved_title": "تم اعتماد الرواتب",
        "payroll_approved_message": "تم اعتماد كشف رواتبك للفترة رقم {{period_id}}.",
        "payroll_paid_title": "تم تسجيل دفعة الرواتب",
        "payroll_paid_message": "تم تسجيل دفعة رواتب بقيمة {{payment_amount}} للفترة رقم {{period_id}}. الرصيد المتبقي: {{balance_amount}}.",
        "payroll_discrepancy_detected_title": "تم اكتشاف فرق في الرواتب",
        "payroll_discrepancy_detected_message": "{{description}}",
    }
)


def normalize_language(value: str | None) -> str:
    if not value:
        return DEFAULT_LANGUAGE

    normalized = value.strip().lower()
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE


def parse_accept_language(header_value: str | None) -> str:
    if not header_value:
        return DEFAULT_LANGUAGE

    for item in header_value.split(","):
        language = item.split(";")[0].strip().lower()
        if not language:
            continue
        base = language.split("-")[0]
        if base in SUPPORTED_LANGUAGES:
            return base
    return DEFAULT_LANGUAGE


def set_current_language(language: str | None) -> Token[str]:
    return _current_language.set(normalize_language(language))


def reset_current_language(token: Token[str]) -> None:
    _current_language.reset(token)


def get_current_language() -> str:
    return normalize_language(_current_language.get())


def resolve_request_language(*, accept_language: str | None = None, user_language: str | None = None) -> str:
    if user_language:
        return normalize_language(user_language)
    return parse_accept_language(accept_language)


def _lookup_translation(language: str, key: str) -> str | None:
    cursor: Any = TRANSLATIONS.get(language, {})
    for part in key.split("."):
        if not isinstance(cursor, Mapping) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor if isinstance(cursor, str) else None


def _interpolate(template: str, params: Mapping[str, Any] | None = None) -> str:
    if not params:
        return template

    value = template
    for key, raw in params.items():
        value = value.replace(f"{{{{{key}}}}}", str(raw))
    return value


def translate(
    key: str,
    params: Mapping[str, Any] | None = None,
    *,
    language: str | None = None,
    fallback: str | None = None,
) -> str:
    resolved_language = normalize_language(language or get_current_language())
    template = _lookup_translation(resolved_language, key)
    if template is None and resolved_language != DEFAULT_LANGUAGE:
        template = _lookup_translation(DEFAULT_LANGUAGE, key)
    if template is None:
        template = fallback or key
    return _interpolate(template, params)


VALIDATION_MESSAGE_MAP = {
    "Field required": "validation.field_required",
    "Invalid value": "validation.invalid_value",
    "At least one target user or role is required": "validation.target_user_or_role_required",
    "Invalid format. Use YYYY-MM": "errors.invalid_month_format",
    "reason is required": "validation.reason_required",
    "field_changed or new_values_json is required for field corrections": "validation.field_or_values_required",
    "target_status is required for smart status corrections": "validation.target_status_required",
    "end_time must be after start_time": "validation.end_time_after_start_time",
    "default_currency is not allowed": "validation.default_currency_not_allowed",
    "default_currency must be a 3-letter ISO currency code": "validation.default_currency_invalid",
    "annual_vacation_days_by_year must be an object keyed by year": "validation.annual_vacation_days_object",
    "annual vacation days must be greater than zero": "validation.annual_vacation_days_positive",
    "max_vacation_carryover_days cannot be negative": "validation.max_carryover_non_negative",
    "carryover_expiry_month must be between 1 and 12": "validation.carryover_expiry_month_range",
    "carryover_expiry_day must be between 1 and 31": "validation.carryover_expiry_day_range",
    "carryover_expiry_month and carryover_expiry_day must both be provided together": "validation.carryover_expiry_both_required",
    "carryover_expiry_day is not valid for the selected month": "validation.carryover_expiry_invalid_for_month",
    "amount must be greater than zero": "validation.amount_positive",
    "reason cannot be empty": "validation.reason_not_empty",
    "username and password are required when create_user_account is true": "validation.username_password_required",
    "end_date must be on or after start_date": "validation.vacation_end_after_start",
    "new_password is too weak": "validation.new_password_weak",
    "new_password may not start or end with whitespace": "validation.new_password_whitespace",
    "Invalid or expired token": "validation.invalid_or_expired_token",
}


def translate_validation_message(message: str) -> str:
    key = VALIDATION_MESSAGE_MAP.get(message)
    if not key and message.startswith("correction_type must be one of "):
        key = "validation.correction_type_invalid"
    if not key and message.startswith("field_changed must be one of "):
        key = "validation.field_changed_invalid"
    if not key and message.startswith("new_values_json keys must be a subset of "):
        key = "validation.new_values_subset_invalid"
    if not key and message.startswith("review_status must be one of "):
        key = "validation.review_status_invalid"
    if not key and message.startswith("adjustment_type must be one of "):
        key = "validation.adjustment_type_invalid"
    if not key and message.startswith("annual_vacation_days_by_year keys must be 4-digit years"):
        key = "validation.annual_vacation_year_key_invalid"
    if not key:
        return message
    return translate(key, fallback=message)


TRANSLATIONS["en"]["validation"].update(
    {
        "reason_required": "Reason is required",
        "correction_type_invalid": "Correction type is invalid",
        "field_changed_invalid": "Changed field is invalid",
        "new_values_subset_invalid": "Correction fields contain unsupported keys",
        "field_or_values_required": "Provide a field change or corrected values",
        "target_status_required": "Target status is required for smart corrections",
        "review_status_invalid": "Review status is invalid",
        "end_time_after_start_time": "End time must be after start time",
        "default_currency_not_allowed": "Default currency is not allowed",
        "default_currency_invalid": "Default currency must be a 3-letter ISO currency code",
        "annual_vacation_days_object": "Annual vacation days by year must be an object keyed by year",
        "annual_vacation_year_key_invalid": "Annual vacation year keys must be 4-digit years",
        "annual_vacation_days_positive": "Annual vacation days must be greater than zero",
        "max_carryover_non_negative": "Maximum carryover days cannot be negative",
        "carryover_expiry_month_range": "Carryover expiry month must be between 1 and 12",
        "carryover_expiry_day_range": "Carryover expiry day must be between 1 and 31",
        "carryover_expiry_both_required": "Carryover expiry month and day must both be provided together",
        "carryover_expiry_invalid_for_month": "Carryover expiry day is not valid for the selected month",
        "adjustment_type_invalid": "Adjustment type is invalid",
        "amount_positive": "Amount must be greater than zero",
        "reason_not_empty": "Reason cannot be empty",
        "username_password_required": "Username and password are required when account creation is enabled",
        "vacation_end_after_start": "End date must be on or after start date",
        "new_password_weak": "New password is too weak",
        "new_password_whitespace": "New password may not start or end with whitespace",
        "invalid_or_expired_token": "Invalid or expired token",
    }
)

TRANSLATIONS["fr"]["validation"].update(
    {
        "reason_required": "Le motif est requis",
        "correction_type_invalid": "Le type de correction est invalide",
        "field_changed_invalid": "Le champ modifie est invalide",
        "new_values_subset_invalid": "Les champs corriges contiennent des cles non prises en charge",
        "field_or_values_required": "Fournissez un changement de champ ou des valeurs corrigees",
        "target_status_required": "Le statut cible est requis pour les corrections intelligentes",
        "review_status_invalid": "Le statut de revision est invalide",
        "end_time_after_start_time": "L'heure de fin doit etre apres l'heure de debut",
        "default_currency_not_allowed": "La devise par defaut n'est pas autorisee",
        "default_currency_invalid": "La devise par defaut doit etre un code ISO a 3 lettres",
        "annual_vacation_days_object": "Les jours de conge annuels par annee doivent etre un objet cle par annee",
        "annual_vacation_year_key_invalid": "Les cles d'annee doivent etre des annees sur 4 chiffres",
        "annual_vacation_days_positive": "Les jours de conge annuels doivent etre superieurs a zero",
        "max_carryover_non_negative": "Le maximum de jours reportes ne peut pas etre negatif",
        "carryover_expiry_month_range": "Le mois d'expiration du report doit etre compris entre 1 et 12",
        "carryover_expiry_day_range": "Le jour d'expiration du report doit etre compris entre 1 et 31",
        "carryover_expiry_both_required": "Le mois et le jour d'expiration du report doivent etre fournis ensemble",
        "carryover_expiry_invalid_for_month": "Le jour d'expiration du report n'est pas valide pour le mois selectionne",
        "adjustment_type_invalid": "Le type d'ajustement est invalide",
        "amount_positive": "Le montant doit etre superieur a zero",
        "reason_not_empty": "Le motif ne peut pas etre vide",
        "username_password_required": "Le nom d'utilisateur et le mot de passe sont requis lorsque la creation de compte est activee",
        "vacation_end_after_start": "La date de fin doit etre egale ou posterieure a la date de debut",
        "new_password_weak": "Le nouveau mot de passe est trop faible",
        "new_password_whitespace": "Le nouveau mot de passe ne peut pas commencer ou se terminer par un espace",
        "invalid_or_expired_token": "Jeton invalide ou expire",
    }
)

TRANSLATIONS["ar"]["validation"].update(
    {
        "reason_required": "السبب مطلوب",
        "correction_type_invalid": "نوع التصحيح غير صالح",
        "field_changed_invalid": "الحقل المعدل غير صالح",
        "new_values_subset_invalid": "حقول التصحيح تحتوي على مفاتيح غير مدعومة",
        "field_or_values_required": "قدّم تغييرًا في الحقل أو قيماً مصححة",
        "target_status_required": "الحالة المستهدفة مطلوبة للتصحيحات الذكية",
        "review_status_invalid": "حالة المراجعة غير صالحة",
        "end_time_after_start_time": "يجب أن يكون وقت الانتهاء بعد وقت البدء",
        "default_currency_not_allowed": "العملة الافتراضية غير مسموح بها",
        "default_currency_invalid": "يجب أن تكون العملة الافتراضية رمز ISO مكوّنًا من 3 أحرف",
        "annual_vacation_days_object": "يجب أن تكون أيام الإجازة السنوية حسب السنة كائنًا مفهرسًا بالسنة",
        "annual_vacation_year_key_invalid": "يجب أن تكون مفاتيح السنة مكوّنة من 4 أرقام",
        "annual_vacation_days_positive": "يجب أن تكون أيام الإجازة السنوية أكبر من صفر",
        "max_carryover_non_negative": "لا يمكن أن يكون الحد الأقصى للترحيل سالبًا",
        "carryover_expiry_month_range": "يجب أن يكون شهر انتهاء الترحيل بين 1 و12",
        "carryover_expiry_day_range": "يجب أن يكون يوم انتهاء الترحيل بين 1 و31",
        "carryover_expiry_both_required": "يجب إدخال شهر ويوم انتهاء الترحيل معًا",
        "carryover_expiry_invalid_for_month": "يوم انتهاء الترحيل غير صالح للشهر المحدد",
        "adjustment_type_invalid": "نوع التعديل غير صالح",
        "amount_positive": "يجب أن يكون المبلغ أكبر من صفر",
        "reason_not_empty": "لا يمكن أن يكون السبب فارغًا",
        "username_password_required": "اسم المستخدم وكلمة المرور مطلوبان عند تفعيل إنشاء الحساب",
        "vacation_end_after_start": "يجب أن يكون تاريخ النهاية في نفس تاريخ البداية أو بعده",
        "new_password_weak": "كلمة المرور الجديدة ضعيفة جدًا",
        "new_password_whitespace": "لا يمكن أن تبدأ كلمة المرور الجديدة أو تنتهي بمسافة",
        "invalid_or_expired_token": "الرمز غير صالح أو منتهي الصلاحية",
    }
)
