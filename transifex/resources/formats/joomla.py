# -*- coding: utf-8 -*-

"""
Joomla INI file handler/compiler
"""
import os, re
import codecs

from transifex.txcommon.log import logger
from transifex.resources.models import SourceEntity
from transifex.resources.formats.utils.decorators import *
from transifex.resources.formats.utils.hash_tag import hash_tag
from transifex.resources.formats.core import Handler, ParseError, CompileError
from transifex.resources.formats.compilation import Compiler
from transifex.resources.formats.resource_collections import StringSet, \
        GenericTranslation


class JoomlaParseError(ParseError):
    pass


class JoomlaCompileError(CompileError):
    pass


class JoomlaCompiler(Compiler):
    """Compiler for Joomla .ini files."""

    def _examine_content(self, content):
        """Determine the version of the file."""
        self.jformat = JoomlaIniVersion.create(content)
        return content

    def _replace_translation(self, original, replacement, text):
        """Modify the translation depending on the version of the file."""
        return super(JoomlaCompiler, self)._replace_translation(
            original, self.jformat.get_compilation(replacement), text
    )

def update_key_dict(obj, key_dict, key, value, rule=5, context="", comment=""):
    """
        obj: Handler object
        key_dict: key_dict from _parse() method of handler
        key: source/key
        value: translation/value
        rule: plural rule
        context: context for key
        comment: comment for key
    """

    try:
        value = obj._unescape(value)
        if key in key_dict and key_dict[key].get(rule, None):
            g = GenericTranslation(key, obj._unescape(
                    key_dict[key][rule]['translation']),
                    context=key_dict[key][rule]['context'],
                    comment=key_dict[key][rule]['comment']
                )
            obj.stringset.strings.remove(g)
            key_dict[key][rule] = {'translation': obj._unescape(value),
                                   'context': context,
                                   'comment': comment
                                  }
        else:
            if key in key_dict:
                key_dict[key][rule] = {
                                        'translation': value,
                                        'context': context,
                                        'comment': comment
                                      }
            else:
                key_dict[key] = {
                            rule: {
                                    'translation': value,
                                    'context': context,
                                    'comment': comment
                                  }
                            }
    except Exception, e:
        logger.warning("Error during parsing: %s" % unicode(e))
    return key_dict


class JoomlaINIHandler(Handler):
    """
    Handler for Joomla's INI translation files.

    See http://docs.joomla.org/Specification_of_language_files
    and http://docs.joomla.org/Creating_a_language_definition_file.
    """

    name = "Joomla *.INI file handler"
    format = "Joomla INI (*.ini)"
    method_name = 'INI'
    comment_chars = ('#', ';', ) # '#' is for 1.5 and ';' for >1.6

    HandlerParseError = JoomlaParseError
    HandlerCompileError = JoomlaCompileError
    CompilerClass = JoomlaCompiler

    def _escape(self, s):
        return  s.replace('\\', '\\\\').replace('\n', r'\\n').replace('\r', r'\\r')

    def _unescape(self, s):
        return s.replace('\\n', '\n').replace('\\r', '\r')

    def _parse(self, is_source, lang_rules):
        """
        Parse an INI file and create a stringset with all entries in the file.
        """
        content = self.content
        self.jformat = JoomlaIniVersion.create(self.content)
        self._find_linesep(content)
        comment = ""
        key_dict = {}

        buf = ''
        for line in self._iter_by_line(content):
            # Skip empty lines and comments
            if not line or line.startswith(self.comment_chars):
                if is_source:
                    buf += line + self.linesep
                    if line.startswith(self.comment_chars):
                        comment = line[1:] + self.linesep
                    else:
                        comment = ""
                continue

            try:
                source, trans = line.split('=', 1)
            except ValueError:
                # Maybe abort instead of skipping?
                logger.warning('Could not parse line "%s". Skipping...' % line)
                continue

            escaped_trans = self.jformat.get_translation(trans)
            if isinstance(self.jformat, JoomlaIniNew):
                trans = trans[1:-1]
            context = ""        # We use empty context

            if is_source:
                if not trans.strip():
                    buf += line + self.linesep
                    continue
                source_len = len(source)
                new_line = line[:source_len] + re.sub(
                    re.escape(trans),
                    "%(hash)s_tr" % {'hash': hash_tag(source, context)},
                    line[source_len:]
                )
                buf += new_line + self.linesep
            elif not SourceEntity.objects.filter(resource=self.resource, string=source).exists()\
                    or not escaped_trans.strip():
                #ignore keys with no translation
                context=""
                continue
            key_dict = update_key_dict(self, key_dict, source,
                    escaped_trans, comment=comment)
            self._add_translation_string(source, self._unescape(escaped_trans),
                    context=context, comment=comment)
            comment = ""
        return buf[:buf.rfind(self.linesep)]


class JoomlaIniVersion(object):
    """Base class for the various formats of Joomla ini files."""

    @classmethod
    def create(cls, content):
        """Factory method to return the correct instance for the format.

        In versions >=1.6 translations are surrounded by double quotes.
        """
        if content[0] == ';':
            return JoomlaIniNew()
        else:
            return JoomlaIniOld()

    def get_translation(self, value):
        """
        Return the trasnlation value extracted from the specified string.
        """
        raise NotImplementedError


class JoomlaIniOld(JoomlaIniVersion):
    """Format for Joomla 1.5."""

    def _escape(self, value):
        return value.replace('"', "&quot;")

    def _unescape(self, value):
        return value.replace("&quot;", '"')

    def get_translation(self, value):
        return self._unescape(value)

    def get_compilation(self, value):
        return self._escape(value)


class JoomlaIniNew(JoomlaIniVersion):
    """Format for Joomla 1.6."""
    def _escape(self, value):
        return value.replace('"', '"_QQ_"')

    def _unescape(self, value):
        return value.replace("&quot;", '"').replace('"_QQ_"', '"')

    def get_translation(self, value):
        # Get rid of double-quote at the start and end of value
        return self._unescape(value[1:-1])

    def get_compilation(self, value):
        return self._escape(value)
