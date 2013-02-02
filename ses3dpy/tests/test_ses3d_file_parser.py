#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test suite for the SES3D file parser.

:copyright:
    Lion Krischer (krischer@geophysik.uni-muenchen.de), 2013
:license:
    GNU General Public License, Version 3
    (http://www.gnu.org/copyleft/gpl.html)
"""
from glob import glob
import inspect
import numpy as np
import os
from StringIO import StringIO
import unittest

from ses3dpy.ses3d_file_parser import is_SES3D, read_SES3D


class SES3DFileParserTestCase(unittest.TestCase):
    """
    Test case for reading SES3D files.
    """
    def setUp(self):
        # Most generic way to get the actual data directory.
        self.data_dir = os.path.join(os.path.dirname(os.path.abspath(
            inspect.getfile(inspect.currentframe()))), "data")

    def test_isSES3DFile(self):
        """
        Tests the isSES3D File function.
        """
        ses3d_files = ["File_theta", "File_phi", "File_r"]
        ses3d_files = [os.path.join(self.data_dir, _i) for _i in ses3d_files]
        for waveform_file in ses3d_files:
            self.assertTrue(is_SES3D(waveform_file))

        # Get some arbitrary other files and assert they are false.
        package_dir = os.path.join(os.path.dirname(os.path.abspath(
            inspect.getfile(inspect.currentframe()))), os.pardir)
        other_files = glob(os.path.join(package_dir, "*.py"))
        for other_file in other_files:
            self.assertFalse(is_SES3D(other_file))

    def test_isSES3DFileWithStringIO(self):
        """
        Same as test_isSES3DFile() but testing from StringIO's
        """
        ses3d_files = ["File_theta", "File_phi", "File_r"]
        ses3d_files = [os.path.join(self.data_dir, _i) for _i in ses3d_files]
        for waveform_file in ses3d_files:
            with open(waveform_file, "r") as open_file:
                waveform_file = StringIO(open_file.read())
            self.assertTrue(is_SES3D(waveform_file))
            waveform_file.close()

        # Get some arbitrary other files and assert they are false.
        package_dir = os.path.join(os.path.dirname(os.path.abspath(
            inspect.getfile(inspect.currentframe()))), os.pardir)
        other_files = glob(os.path.join(package_dir, "*.py"))
        for other_file in other_files:
            with open(other_file, "r") as open_file:
                other_file = StringIO(open_file.read())
            self.assertFalse(is_SES3D(other_file))
            other_file.close()

    def test_readingSES3DFile(self):
        """
        Tests the actual reading of a SES3D file.
        """
        filename = os.path.join(self.data_dir, "File_phi")
        st = read_SES3D(filename)
        self.assertEqual(len(st), 1)
        tr = st[0]
        self.assertEqual(len(tr), 3300)
        self.assertAlmostEqual(tr.stats.delta, 0.15)
        # Latitude in the file is actually the colatitude.
        self.assertAlmostEqual(tr.stats.ses3d.receiver_latitude, 90.0 -
            107.84100)
        self.assertAlmostEqual(tr.stats.ses3d.receiver_longitude, -3.5212801)
        self.assertAlmostEqual(tr.stats.ses3d.receiver_depth_in_m, 0.0)
        self.assertAlmostEqual(tr.stats.ses3d.source_latitude, 90.0 -
            111.01999)
        self.assertAlmostEqual(tr.stats.ses3d.source_longitude, -8.9499998)
        self.assertAlmostEqual(tr.stats.ses3d.source_depth_in_m, 20000)
        # Test head and tail of the actual data. Assume the rest to be correct
        # as well.
        np.testing.assert_array_equal(tr.data[:50],
            np.zeros(50, dtype="float32"))
        # The data is just copied from the actual file.
        np.testing.assert_almost_equal(tr.data[-9:], np.array([3.41214417E-07,
            2.95646032E-07, 2.49543859E-07, 2.03108399E-07, 1.56527761E-07,
            1.09975687E-07, 6.36098676E-08, 1.75719919E-08, -2.80116144E-08]))

    def test_readingSES3DFileFromStringIO(self):
        """
        Same as test_readingSES3DFile() but with the data given as a StringIO.
        """
        filename = os.path.join(self.data_dir, "File_phi")
        with open(filename, "rb") as open_file:
            file_object = StringIO(open_file.read())
        st = read_SES3D(file_object)
        file_object.close()
        self.assertEqual(len(st), 1)
        tr = st[0]
        self.assertEqual(len(tr), 3300)
        self.assertAlmostEqual(tr.stats.delta, 0.15)
        # Latitude in the file is actually the colatitude.
        self.assertAlmostEqual(tr.stats.ses3d.receiver_latitude, 90.0 -
            107.84100)
        self.assertAlmostEqual(tr.stats.ses3d.receiver_longitude, -3.5212801)
        self.assertAlmostEqual(tr.stats.ses3d.receiver_depth_in_m, 0.0)
        self.assertAlmostEqual(tr.stats.ses3d.source_latitude, 90.0 -
            111.01999)
        self.assertAlmostEqual(tr.stats.ses3d.source_longitude, -8.9499998)
        self.assertAlmostEqual(tr.stats.ses3d.source_depth_in_m, 20000)
        # Test head and tail of the actual data. Assume the rest to be correct
        # as well.
        np.testing.assert_array_equal(tr.data[:50],
            np.zeros(50, dtype="float32"))
        # The data is just copied from the actual file.
        np.testing.assert_almost_equal(tr.data[-9:], np.array([3.41214417E-07,
            2.95646032E-07, 2.49543859E-07, 2.03108399E-07, 1.56527761E-07,
            1.09975687E-07, 6.36098676E-08, 1.75719919E-08, -2.80116144E-08]))

    def test_ComponentMapping(self):
        """
        Tests that the components are correctly mapped.
        """
        filename_theta = os.path.join(self.data_dir, "File_theta")
        filename_phi = os.path.join(self.data_dir, "File_phi")
        filename_r = os.path.join(self.data_dir, "File_r")

        # The x-component points east.
        tr_theta = read_SES3D(filename_theta)[0]
        self.assertEqual(tr_theta.stats.channel, "N")

        # The x-component points south, but is inverted, thus north.
        tr_phi = read_SES3D(filename_phi)[0]
        self.assertEqual(tr_phi.stats.channel, "E")

        # The z-component points up.
        tr_r = read_SES3D(filename_r)[0]
        self.assertEqual(tr_r.stats.channel, "Z")

    def test_NorthComponentIsInvertedSouthComponent(self):
        """
        SES3D return south oriented data. The reader inverts it to return north
        oriented data.
        """
        filename = os.path.join(self.data_dir, "File_theta")
        tr = read_SES3D(filename)[0]
        self.assertEqual(tr.stats.channel, "N")
        # The data actually in the file. This points south.
        data = np.array([4.23160685E-07, 3.80973177E-07, 3.39335969E-07,
            2.98305707E-07, 2.57921158E-07, 2.18206054E-07, 1.79171423E-07,
            1.40820376E-07, 1.03153077E-07, 6.61708626E-08])
        # Invert the data.
        data *= -1.0
        # Check.
        np.testing.assert_almost_equal(tr.data[-10:], data)


def suite():
    return unittest.makeSuite(SES3DFileParserTestCase, "test")


if __name__ == "__main__":
    unittest.main(defaultTest="suite")
