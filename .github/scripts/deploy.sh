set -x
rm -r dist build logica.egg-info
yes | rm -r logica
git clone https://github.com/evgskv/logica
cp __main__.py logica/
python3 setup.py sdist bdist_wheel
python3 -m twine upload --repository pypi dist/*