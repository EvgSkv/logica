import sys

from common import color
from logging import info


class TypeInferenceException(Exception):

  def ShowMessage(self):
    info(color.Format('{underline}Infering types{end}:'))
    info(f'{color.Format("[ {error}Error{end} ]")} {str(self)}')
