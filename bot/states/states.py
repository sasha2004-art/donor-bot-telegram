from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    awaiting_full_name = State()
    awaiting_category = State()
    awaiting_consent = State()
    awaiting_university = State()
    awaiting_custom_university_name = State()
    awaiting_faculty = State()
    awaiting_custom_faculty_name = State()
    awaiting_study_group = State()
    awaiting_gender = State()


class EventCreation(StatesGroup):
    awaiting_name = State()
    awaiting_datetime = State()
    awaiting_location_text = State()
    awaiting_location_point = State()
    awaiting_blood_center = State()
    awaiting_new_blood_center_name = State()
    awaiting_donation_type = State()
    # awaiting_points = State()
    awaiting_limit = State()
    awaiting_confirmation = State()


'''
class MerchCreation(StatesGroup):
    awaiting_photo = State()
    awaiting_name = State()
    awaiting_description = State()
    awaiting_price = State()
'''


'''
class PointsChange(StatesGroup):
    awaiting_user_id = State()
    awaiting_points_amount = State()
    awaiting_reason = State()
'''


class ManualWaiver(StatesGroup):
    awaiting_end_date = State()
    awaiting_reason = State()


class Mailing(StatesGroup):
    awaiting_message_text = State()
    awaiting_media = State()
    awaiting_audience_type = State()
    awaiting_audience_value = State()
    awaiting_audience_choice = State()
    awaiting_event_choice = State()
    awaiting_confirmation = State()


class AdminManagement(StatesGroup):
    awaiting_user_to_promote = State()
    awaiting_user_to_demote = State()


class BlockUser(StatesGroup):
    awaiting_user_id = State()
    awaiting_reason = State()
    awaiting_user_id_unblock = State()


class VolunteerActions(StatesGroup):
    awaiting_qr_photo = State()
    awaiting_confirmation = State()


class EventEditing(StatesGroup):
    choosing_field = State()
    awaiting_new_value = State()
    awaiting_new_blood_center_name_for_edit = State()


'''
class MerchEditing(StatesGroup):
    choosing_field = State()
    awaiting_new_value = State()
'''


class UserSearch(StatesGroup):
    awaiting_query = State()


class UserWaiver(StatesGroup):
    awaiting_end_date = State()
    awaiting_reason = State()


class FeedbackSurvey(StatesGroup):
    awaiting_well_being = State()
    awaiting_well_being_comment = State()
    awaiting_organization_score = State()
    awaiting_what_liked = State()
    awaiting_what_disliked = State()
    awaiting_other_suggestions = State()


class AdminAnalytics(StatesGroup):
    choosing_event_for_analysis = State()


class AdminAddUser(StatesGroup):
    awaiting_phone = State()
    awaiting_full_name = State()
    awaiting_category = State()
    awaiting_consent = State()
    awaiting_university = State()
    awaiting_custom_university_name = State()
    awaiting_faculty = State()
    awaiting_custom_faculty_name = State()
    awaiting_study_group = State()
    awaiting_gender = State()


class PostEventProcessing(StatesGroup):
    choosing_event = State()
    marking_participants = State()


class EditInfoSection(StatesGroup):
    choosing_section = State()
    awaiting_new_text = State()


class AskQuestion(StatesGroup):
    awaiting_question = State()


class AnswerQuestion(StatesGroup):
    awaiting_answer = State()


class DataImport(StatesGroup):
    awaiting_file = State()
    awaiting_old_db_file = State()


class UserEditing(StatesGroup):
    choosing_field = State()
    awaiting_new_value = State()
