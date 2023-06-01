from logging import info

from common import color


class TypeInferenceException(Exception):
  def ShowMessage(self):
    info(color.Format('{underline}Infering types{end}:'))
    info(f'{color.Format("[ {error}Error{end} ]")} {str(self)}')
