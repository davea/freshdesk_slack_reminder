upload:
	rsync --exclude venv -Ppa . ${UPLOAD_DESTINATION}

venv:
	python3 -m venv venv
	venv/bin/pip install -r requirements.txt

clean:
	rm -rf venv
