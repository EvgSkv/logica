import sys

from common import color


class TypeInferenceException(Exception):

  def ShowMessage(self, stream=sys.stderr):
    print(color.Format('{underline}Infering types{end}:'), file=stream)
    print(color.Format('[ {error}Error{end} ] ') + str(self), file=stream)
