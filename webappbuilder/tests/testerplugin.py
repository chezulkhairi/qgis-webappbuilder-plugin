# -*- coding: utf-8 -*-
#
# (c) 2016 Boundless, http://boundlessgeo.com
# This code is licensed under the GPL 2.0 license.
#
import unittest
import webbrowser
import os
import settingstest
import widgetstest
import appdefvaliditytest
import sdkservicetest
from webappbuilder.tests.utils import (loadTestProject, createAppFromTestAppdef,
                                       openWAB, closeWAB, testAppdef, _setWrongSdkEndpoint,
                                       _resetSdkEndpoint, widgets, widgetTestAbout,
                                       setNetworkTimeout, resetNetworkTimeout,
                                       getWABDialog, hideWAB)
from qgis.utils import iface
from PyQt4.QtTest import QTest
from PyQt4.QtGui import QMessageBox
from PyQt4.QtCore import Qt, QEventLoop
from webappbuilder.utils import getConnectAuthCfg, topics

try:
    from qgis.core import QGis
except ImportError:
    from qgis.core import Qgis as QGis

webAppFolder = None

def settings():
    return  {"WEB_APP_OUTPUT_FOLDER": ""}

def functionalTests():
    # create TestCase instance to use Assert methods
    tc = unittest.TestCase('__init__')

    try:
        from qgistester.test import Test
        from qgistester.utils import layerFromName
    except:
        return []

    def _createWebApp(n, preview=True, aboutContent=None):
        global webAppFolder
        webAppFolder = createAppFromTestAppdef(n, preview, aboutContent)

    tests = []

    appdefFolder = os.path.join(os.path.dirname(__file__), "data")

    def _testWidget(n):
        aboutContent = widgetTestAbout.get(n, None)
        test = Test("Verify '%s' widget" % n, "Widget tests")
        test.addStep("Setting up project", lambda: loadTestProject("widgets"))
        test.addStep("Creating web app", lambda: _createWebApp(n, True, aboutContent))
        test.addStep("Verify web app in browser", prestep=lambda: webbrowser.open_new(
                    "file:///" + webAppFolder.replace("\\","/") + "/webapp/index_debug.html"))
        return test

    for w in widgets:
        for i in ["", "2", "3"]:
            testName = w+i
            f = os.path.join(appdefFolder, "%s.appdef" % testName)
            if os.path.exists(f):
                tests.append(_testWidget(testName))

    def _openComparison(n):
        webbrowser.open_new("file:///" + os.path.dirname(__file__).replace("\\","/")
                            + "/expected/apps/%s/index_debug.html" % n)
        webbrowser.open_new("file:///" + webAppFolder.replace("\\","/")
                            + "/webapp/index_debug.html")

    def _comparisonTest(n):
        test = Test("Symbology test '%s'" % n, "Symbology tests")
        test.addStep("Setting up project", lambda: loadTestProject(n))
        test.addStep("Creating web app", lambda: _createWebApp(n))
        test.addStep("Compare web app with expected app in browser",
                     prestep=lambda: _openComparison(n))
        return test

    comparisonTests = ["points", "points2", "osm", "polygons", "labels", "arrows"]
    for t in comparisonTests:
        tests.append(_comparisonTest(t))

    def _createWebAppCompiled(n):
        from pubsub import pub
        def endWriteWebAppListener(success, reason):
            from pubsub import pub
            pub.unsubscribe(endWriteWebAppListener, topics.endWriteWebApp)
            loop.exit()
        loop = QEventLoop()
        pub.subscribe(endWriteWebAppListener , topics.endWriteWebApp)
        _createWebApp(n, False)
        loop.exec_(flags = QEventLoop.ExcludeUserInputEvents)

    def _openComparisonCompiled(n):
        webbrowser.open_new("file:///" + os.path.dirname(__file__).replace("\\","/")
                            + "/expected/apps/%s/index_debug.html" % n)
        webbrowser.open_new("http://localhost/webapp/index.html")

    def _checkConnect():
        getConnectAuthCfg()

    def _comparisonTestCompiled(n):
        test = Test("Compiled app test '%s'" % n, "Compiled app tests")
        test.addStep("Setting up project", lambda: loadTestProject("widgets"))
        test.addStep("Creating web app", lambda: _createWebAppCompiled(n), prestep = _checkConnect)
        test.addStep("Compare web app with expected app in browser",
                     prestep=lambda: _openComparisonCompiled(n))
        return test

    comparisonTestsCompiled = ["basic", "tabbed"]
    for t in comparisonTestsCompiled:
        tests.append(_comparisonTestCompiled(t))

    unconfiguredBookmarksTest = Test("Verify bookmarks widget cannot be used if no bookmarks defined")
    unconfiguredBookmarksTest.addStep("Load project", lambda: loadTestProject())
    unconfiguredBookmarksTest.addStep("Open WAB", lambda: openWAB())
    unconfiguredBookmarksTest.addStep("Try to create an app with the bookmarks widget, without configuring it to add bookmarks.\n"
                         "Verify it shows a warning.")
    unconfiguredBookmarksTest.setCleanup(closeWAB)
    tests.append(unconfiguredBookmarksTest)

    unsupportedSymbologyTest = Test("Verify warning for unsupported symbology")
    unsupportedSymbologyTest.addStep("Load project", lambda: loadTestProject())
    unsupportedSymbologyTest.addStep("Open WAB", openWAB)
    unsupportedSymbologyTest.addStep("Click on 'Preview'. Verify a warning about unsupported symbology is shown.")
    unsupportedSymbologyTest.setCleanup(closeWAB)
    tests.append(unsupportedSymbologyTest)

    wrongLogoTest = Test("Verify warning for wrong logo file")
    wrongLogoTest.addStep("Load project", lambda: loadTestProject())
    wrongLogoTest.addStep("Open WAB", openWAB)
    wrongLogoTest.addStep("Enter 'wrong' in the logo textbox and click on 'Preview'."
                                     "The logo texbox should get a yellow background.")
    wrongLogoTest.setCleanup(closeWAB)
    tests.append(wrongLogoTest)


    nodataTest = Test("Verify that NODATA values are transparent")
    nodataTest.addStep("Load project", lambda: loadTestProject("nodata"))
    nodataTest.addStep("Creating web app", lambda: _createWebApp("nodata"))
    nodataTest.addStep("Verify web app in browser. NODATA values should be transparent. "
                       "<b>NOTE</b> don't use Chrome/Chromium to check this web app they "
                       "have bug and it might not work as expected. Use Firefox or another browser.",
                       prestep=lambda: webbrowser.open_new(
                             "file:///" + webAppFolder.replace("\\","/") + "/webapp/index_debug.html"))
    tests.append(nodataTest)

    createEmpyAppTest = Test("Verify preview an app with no layers")
    createEmpyAppTest.addStep("Load project", iface.newProject)
    createEmpyAppTest.addStep("Open WAB", lambda: openWAB())
    createEmpyAppTest.addStep("Create an app preview and check it is correctly created")
    createEmpyAppTest.setCleanup(closeWAB)
    tests.append(createEmpyAppTest)

    wrongEndpointTest = Test("Verify wrong SDK service URL")
    wrongEndpointTest.addStep("Load project", iface.newProject)
    wrongEndpointTest.addStep("Load project", _setWrongSdkEndpoint)
    wrongEndpointTest.addStep("Open WAB", lambda: openWAB())
    wrongEndpointTest.addStep("Try to create an app and check it complains of a wrong URL")
    wrongEndpointTest.setCleanup(_resetSdkEndpoint)
    tests.append(wrongEndpointTest)

    wmsTimeinfoTest = Test("Verify that spatio-temporal WMS layers supported")
    wmsTimeinfoTest.addStep("Load project", lambda: loadTestProject("wms-timeinfo-interval"))
    wmsTimeinfoTest.addStep("Creating web app", lambda: _createWebApp("wms-timeinfo-interval"))
    wmsTimeinfoTest.addStep("Verify web app in browser.", prestep=lambda: webbrowser.open_new(
                             "file:///" + webAppFolder.replace("\\","/") + "/webapp/index_debug.html"))
    tests.append(wmsTimeinfoTest )

    try:
        from boundlessconnect.tests.testerplugin import _startConectPlugin
        denyCompilationTest = Test("Verify deny compilation for invalid Connect credentials", "SDK Connection tests")
        denyCompilationTest.addStep("Reset project", iface.newProject)
        denyCompilationTest.addStep('Enter invalid Connect credentials and accept dialog by pressing "Login" button.\n'
                                'Check that Connect shows Warning message complaining about only open access permissions.'
                                'Close error message by pressing "Yes" button.',
                        prestep=lambda: _startConectPlugin(), isVerifyStep=True)
        denyCompilationTest.addStep("Open WAB", lambda: openWAB())
        denyCompilationTest.addStep("Create an EMPTY app and check it complains of a permission denied")
        denyCompilationTest.setCleanup(closeWAB)
        tests.append(denyCompilationTest)
        
        localTimeoutCompilationTest = Test("Verify compilation timeout due to local settings", "SDK Connection tests")
        localTimeoutCompilationTest.addStep("Reset project", iface.newProject)
        localTimeoutCompilationTest.addStep('Enter EnterpriseTestDesktop Connect credentials and accept dialog by pressing "Login" button.\n'
                                    'Check that Connect is logged showing EnterpriseTestDesktop@boundlessgeo.com in the bottom',
                            prestep=lambda: _startConectPlugin(), isVerifyStep=True)
        localTimeoutCompilationTest.addStep("Open WAB", lambda: openWAB())
        localTimeoutCompilationTest.addStep("Setting timeout", lambda: setNetworkTimeout(value=3000))
        localTimeoutCompilationTest.addStep("Create an EMPTY app and check it complains of network timeout", isVerifyStep=True)
        localTimeoutCompilationTest.addStep("Close WAB", closeWAB)
        localTimeoutCompilationTest.setCleanup(resetNetworkTimeout)
        tests.append(localTimeoutCompilationTest)

        successCompilationTest = Test("Verify successful compilation with EnterpriseTestDesktop", "SDK Connection tests")
        successCompilationTest.addStep("Reset project", iface.newProject)
        successCompilationTest.addStep('Enter EnterpriseTestDesktop Connect credentials and accept dialog by pressing "Login" button.\n'
                                    'Check that Connect is logged showing EnterpriseTestDesktop@boundlessgeo.com in the bottom',
                            prestep=lambda: _startConectPlugin(), isVerifyStep=True)
        successCompilationTest.addStep("Open WAB", lambda: openWAB())
        successCompilationTest.addStep("Create an EMPTY app and check it successfully ends", isVerifyStep=True)
        successCompilationTest.setCleanup(closeWAB)
        tests.append(successCompilationTest)

        wrongTierCompilationTest = Test("Verify cannot compile with wrong tier", "SDK Connection tests")
        wrongTierCompilationTest.addStep("Reset project", iface.newProject)
        wrongTierCompilationTest.addStep('Enter BasicTestDesktop Connect credentials and accept dialog by pressing "Login" button.\n'
                                    'Check that Connect is logged showing BasicTestDesktop@boundlessgeo.com in the bottom',
                            prestep=lambda: _startConectPlugin(), isVerifyStep=True)
        wrongTierCompilationTest.addStep("Open WAB", lambda: openWAB())
        wrongTierCompilationTest.addStep("Try to create an app and verify it fails", isVerifyStep=True)
        wrongTierCompilationTest.setCleanup(closeWAB)
        tests.append(wrongTierCompilationTest)

        # test stopCompilationTest
        def checkStartoStopButton(text=None):
            dlg = getWABDialog()
            tc.assertIn(dlg.buttonCreateOrStopApp.text(), text)

        def clickStopButton(after=5000):
            QTest.qWait(after)
            dlg = getWABDialog()
            QTest.mouseClick(dlg.buttonCreateOrStopApp, Qt.LeftButton)

        stopCompilationTest = Test("Verify stop compilation with EnterpriseTestDesktop user", "SDK Connection tests")
        stopCompilationTest.addStep("Reset project", iface.newProject)
        stopCompilationTest.addStep('Enter EnterpriseTestDesktop Connect credentials and accept dialog by pressing "Login" button.\n'
                                    'Check that Connect is logged showing EnterpriseTestDesktop@boundlessgeo.com in the bottom',
                            prestep=lambda: _startConectPlugin(), isVerifyStep=True)
        stopCompilationTest.addStep("Open WAB", lambda: openWAB())
        stopCompilationTest.addStep("Create an EMPTY app and start compilation, then click on next step!")
        stopCompilationTest.addStep("Verify if stop button is set", lambda: checkStartoStopButton(text='Stop') )
        stopCompilationTest.addStep("Click stop", lambda: clickStopButton(after=1000) )
        stopCompilationTest.addStep("Verify if StartApp button is set", lambda: checkStartoStopButton(text='CreateApp') )
        stopCompilationTest.setCleanup(closeWAB)
        tests.append(stopCompilationTest)
    except ImportError:
        pass

    return tests


def unitTests():
    _tests = []
    _tests.extend(settingstest.suite())
    _tests.extend(widgetstest.suite())
    _tests.extend(appdefvaliditytest.suite())
    _tests.extend(sdkservicetest.suite())
    return _tests
