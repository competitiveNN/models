#!/bin/bash
echo "MARKER_TEST_START"
touch /work/marker.txt
echo "marker_rc=$?"
ls -la /work/marker.txt
date > /work/marker_date.txt
echo "MARKER_TEST_END"