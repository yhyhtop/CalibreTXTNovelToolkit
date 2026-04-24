import os
import re
import shutil
import subprocess
import sys
import traceback

from qt.core import QAction, QFileDialog, QMenu

from calibre.ebooks.metadata.book.base import Metadata
from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre.utils.date import parse_only_date, utcnow


SMALL_FILE_LIMIT = 500 * 1024
SMALL_FILE_SERIES = '太短了，先养一养'
DEFAULT_SERIES = '未导入'
DUPLICATE_TAG = '重复'
IMPORT_PUBDATE = parse_only_date('2000-12-31')
DEFAULT_PUBLISHER = '中国成人文学精选'


class ParseError(ValueError):
    pass


class ParsedNovel:
    def __init__(self, path, title, author, middle, comment, size):
        self.path = path
        self.title = title.strip()
        self.author = author.strip()
        self.middle = middle.strip()
        self.comment = comment.strip()
        self.size = size

    @property
    def is_small(self):
        return self.size < SMALL_FILE_LIMIT

    @property
    def status_text(self):
        return self.middle

    @property
    def is_finished(self):
        text = self.status_text
        has_finished = any(x in text for x in ('完结', '完本', '全本'))
        has_negative = any(x in text for x in ('未完结', '未完本', '未全本'))
        return has_finished and not has_negative

    @property
    def is_serial(self):
        return (not self.is_finished) and '连载' in self.status_text

    @property
    def is_stalled(self):
        return '断更' in self.status_text

    @property
    def should_update_existing(self):
        return self.is_serial

    @property
    def should_mark_duplicate_if_matched(self):
        return self.is_finished or self.is_stalled


def parse_standard_filename(path):
    filename = os.path.basename(path)
    stem, ext = os.path.splitext(filename)
    if ext.lower() != '.txt':
        raise ParseError('不是 TXT 文件')

    match = re.match(r'^《(?P<title>[^》]+)》\s*(?P<middle>.*?)\s*作者[：:]\s*(?P<author>.+)$', stem)
    if not match:
        raise ParseError('文件名不符合： 《书名》 起始-结束章 状态 作者：作者.txt')

    title = match.group('title').strip()
    author = match.group('author').strip()
    middle = match.group('middle').strip()
    if not title:
        raise ParseError('文件名缺少书名')
    if not author:
        raise ParseError('文件名缺少作者')

    return ParsedNovel(path, title, author, middle, stem, os.path.getsize(path))


def status_tag(parsed):
    if parsed.is_finished:
        return '完结'
    if parsed.is_stalled:
        return '断更'
    if parsed.is_serial:
        return '连载'
    return None


def generated_tag(parsed):
    text = parsed.status_text
    status = status_tag(parsed)
    has_l = 'L' in text or '加料' in text

    for keyword in ('调教', '母女', '母子', '文学', '自购'):
        if keyword in text:
            return keyword

    if 'NTR' in text:
        parts = ['NTR']
    elif '刺猬猫' in text:
        parts = ['刺猬猫']
    elif '起点' in text:
        parts = ['起点']
    elif status:
        parts = ['刘备']
    elif has_l:
        return '加料'
    else:
        return '刘备'

    if status:
        parts.append(status)
    if has_l and parts and parts[0] == '刘备':
        parts.append('加料')
    return '、'.join(parts)


def normalize_authors(authors):
    if not authors:
        return []
    if isinstance(authors, str):
        return [x.strip() for x in authors.split('&') if x.strip()]
    return [str(x).strip() for x in authors if str(x).strip()]


def prepend_comment_line(new_line, old_comments, limit=5):
    old_comments = old_comments or ''
    # Comments created by this plugin are plain text. Strip simple HTML if the
    # field was edited by calibre's rich text editor before this import.
    old_comments = comments_to_plain_text(old_comments)
    lines = [new_line.strip()]
    lines.extend(x.strip() for x in old_comments.splitlines() if x.strip())
    return '\n'.join(lines[:limit])


def comments_to_plain_text(comments):
    comments = comments or ''
    comments = re.sub(r'(?i)<br\s*/?>', '\n', comments)
    comments = re.sub(r'(?i)</p\s*>', '\n', comments)
    comments = re.sub(r'<[^>]+>', '', comments)
    return comments


def first_comment_line(comments):
    for line in comments_to_plain_text(comments).splitlines():
        line = line.strip()
        if line:
            return line
    return ''


def safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', '_', name or '')
    name = name.strip().rstrip('.')
    return name or '未命名'


def unique_destination_path(directory, stem, ext='.txt'):
    stem = safe_filename(stem)
    path = os.path.join(directory, stem + ext)
    if not os.path.exists(path):
        return path
    counter = 2
    while True:
        candidate = os.path.join(directory, '{} ({}){}'.format(stem, counter, ext))
        if not os.path.exists(candidate):
            return candidate
        counter += 1


class TxtNovaToolkitAction(InterfaceAction):
    name = 'TXT Nova Toolkit'
    action_spec = ('TXT Nova Toolkit', None, '导入、更新和导出 TXT 小说', None)

    def genesis(self):
        icon = get_icons('images/icon.png', self.name)
        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.run)

        menu = QMenu(self.gui)
        import_action = QAction(icon, '导入/更新 TXT 小说', self.gui)
        import_action.triggered.connect(self.run)
        export_action = QAction('导出选中 TXT 小说', self.gui)
        export_action.triggered.connect(self.export_selected_txt)
        menu.addAction(import_action)
        menu.addAction(export_action)
        self.qaction.setMenu(menu)

    def run(self):
        files, _ = QFileDialog.getOpenFileNames(
            self.gui,
            '选择 TXT 小说文件',
            '',
            'TXT files (*.txt);;All files (*)'
        )
        if not files:
            return

        results = []
        changed_ids = set()
        for path in files:
            try:
                action, book_id = self.process_file(str(path))
                if book_id is not None:
                    changed_ids.add(book_id)
                results.append(('成功', os.path.basename(path), action))
            except Exception as err:
                details = '{}\n{}'.format(err, traceback.format_exc())
                results.append(('失败', os.path.basename(path), details))

        self.refresh_gui(changed_ids)
        self.show_summary(results)

    def process_file(self, path):
        parsed = parse_standard_filename(path)
        matches = self.find_existing_books(parsed.title, parsed.author)

        if parsed.should_update_existing:
            if len(matches) == 1:
                return self.update_existing(matches[0], parsed), matches[0]
            if len(matches) > 1:
                raise RuntimeError('找到多个同书名同作者记录，已跳过，请手动处理')
            book_id = self.add_new_book(parsed, duplicate=False)
            return '新增连载书籍 #{}'.format(book_id), book_id

        duplicate = parsed.should_mark_duplicate_if_matched and bool(matches)
        book_id = self.add_new_book(parsed, duplicate=duplicate)
        if duplicate:
            return '新增重复记录 #{}'.format(book_id), book_id
        return '新增书籍 #{}'.format(book_id), book_id

    def find_existing_books(self, title, author):
        db = self.gui.current_db.new_api
        matches = []
        wanted_title = title.strip()
        wanted_author = author.strip()
        for book_id in db.all_book_ids():
            current_title = db.field_for('title', book_id) or ''
            if str(current_title).strip() != wanted_title:
                continue
            authors = normalize_authors(db.field_for('authors', book_id))
            joined_authors = ' & '.join(authors)
            if authors == [wanted_author] or joined_authors == wanted_author:
                matches.append(book_id)
        return matches

    def make_metadata(self, parsed, duplicate=False):
        mi = Metadata(parsed.title, [parsed.author])
        mi.comments = parsed.comment
        mi.tags = [DUPLICATE_TAG if duplicate else generated_tag(parsed)]
        mi.series = SMALL_FILE_SERIES if parsed.is_small else DEFAULT_SERIES
        mi.series_index = 1.0
        mi.timestamp = utcnow()
        mi.pubdate = IMPORT_PUBDATE
        mi.publisher = DEFAULT_PUBLISHER
        mi.author_sort = parsed.author
        return mi

    def add_new_book(self, parsed, duplicate=False):
        mi = self.make_metadata(parsed, duplicate=duplicate)
        return self.gui.current_db.import_book(
            mi,
            [parsed.path],
            notify=True,
            import_hooks=True,
            apply_import_tags=False
        )

    def update_existing(self, book_id, parsed):
        legacy_db = self.gui.current_db
        db = legacy_db.new_api
        now = utcnow()
        old_comments = db.field_for('comments', book_id) or ''
        comments = prepend_comment_line(parsed.comment, old_comments)

        self.remove_non_txt_formats(book_id)
        legacy_db.add_format_with_hooks(book_id, 'TXT', parsed.path, index_is_id=True, replace=True)

        updates = {
            'comments': {book_id: comments},
            'timestamp': {book_id: now},
            'pubdate': {book_id: IMPORT_PUBDATE},
        }
        if parsed.is_small:
            updates['series'] = {book_id: SMALL_FILE_SERIES}
        if not (db.field_for('publisher', book_id) or '').strip():
            updates['publisher'] = {book_id: DEFAULT_PUBLISHER}

        for field, value_map in updates.items():
            db.set_field(field, value_map, allow_case_change=True)

        existing_tags = list(db.field_for('tags', book_id) or ())
        if not existing_tags:
            legacy_db.set_tags(book_id, [generated_tag(parsed)], notify=False)

        legacy_db.update_last_modified((book_id,), now=now)
        legacy_db.notify('metadata', [book_id])
        return '更新连载书籍 #{}，已覆盖 TXT 并删除旧派生格式'.format(book_id)

    def remove_non_txt_formats(self, book_id):
        legacy_db = self.gui.current_db
        formats = legacy_db.formats(book_id, index_is_id=True) or ''
        for fmt in [x.strip() for x in formats.split(',') if x.strip()]:
            if fmt.upper() != 'TXT':
                legacy_db.remove_format(book_id, fmt, index_is_id=True, notify=False)

    def export_selected_txt(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            return error_dialog(self.gui, '无法导出 TXT 小说', '请先在书库中选择至少一本书。', show=True)

        model = self.gui.library_view.model()
        book_ids = [model.id(row) for row in rows]
        directory = QFileDialog.getExistingDirectory(self.gui, '选择 TXT 导出目录', '')
        if not directory:
            return
        directory = str(directory)

        results = []
        for book_id in book_ids:
            try:
                destination = self.export_one_txt(book_id, directory)
                results.append(('成功', str(book_id), os.path.basename(destination)))
            except Exception as err:
                details = '{}\n{}'.format(err, traceback.format_exc())
                results.append(('失败', str(book_id), details))
        self.open_directory(directory, results)
        self.show_export_summary(results)

    def export_one_txt(self, book_id, directory):
        legacy_db = self.gui.current_db
        db = legacy_db.new_api
        if not legacy_db.has_format(book_id, 'TXT', index_is_id=True):
            title = db.field_for('title', book_id) or '未知书名'
            raise RuntimeError('《{}》没有 TXT 格式'.format(title))

        comments = db.field_for('comments', book_id) or ''
        stem = first_comment_line(comments)
        if not stem:
            title = db.field_for('title', book_id) or '未知书名'
            authors = normalize_authors(db.field_for('authors', book_id))
            stem = '{} - {}'.format(title, ' & '.join(authors) if authors else '佚名')

        source = legacy_db.format_abspath(book_id, 'TXT', index_is_id=True)
        if not source or not os.path.exists(source):
            raise RuntimeError('TXT 文件不存在或无法访问')

        destination = unique_destination_path(directory, stem, '.txt')
        shutil.copyfile(source, destination)
        return destination

    def open_directory(self, directory, results):
        try:
            if sys.platform.startswith('win'):
                os.startfile(directory)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', directory])
            else:
                subprocess.Popen(['xdg-open', directory])
        except Exception as err:
            results.append(('失败', '打开目录', '{}\n{}'.format(err, traceback.format_exc())))

    def refresh_gui(self, changed_ids):
        if not changed_ids:
            return
        try:
            model = self.gui.library_view.model()
            if hasattr(model, 'refresh_ids'):
                model.refresh_ids(changed_ids)
            if hasattr(model, 'refresh'):
                model.refresh()
        except Exception:
            traceback.print_exc()
        try:
            self.gui.tags_view.recount()
        except Exception:
            pass

    def show_summary(self, results):
        ok = [x for x in results if x[0] == '成功']
        failed = [x for x in results if x[0] != '成功']
        lines = []
        for status, name, message in results:
            lines.append('[{}] {} - {}'.format(status, name, message))
        message = '成功：{} 本；失败：{} 本'.format(len(ok), len(failed))
        details = '\n'.join(lines)
        if failed:
            error_dialog(self.gui, 'TXT 小说导入/更新完成', message, det_msg=details, show=True)
        else:
            info_dialog(self.gui, 'TXT 小说导入/更新完成', message, det_msg=details, show=True)

    def show_export_summary(self, results):
        ok = [x for x in results if x[0] == '成功']
        failed = [x for x in results if x[0] != '成功']
        lines = []
        for status, book_id, message in results:
            lines.append('[{}] #{} - {}'.format(status, book_id, message))
        message = '成功导出：{} 本；失败：{} 本'.format(len(ok), len(failed))
        details = '\n'.join(lines)
        if failed:
            error_dialog(self.gui, 'TXT 小说导出完成', message, det_msg=details, show=True)
        else:
            info_dialog(self.gui, 'TXT 小说导出完成', message, det_msg=details, show=True)
